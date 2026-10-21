#!/usr/bin/env python3
"""Typed client for OEC's isolated multimodal model sidecars."""
from __future__ import annotations
import argparse,base64,hashlib,ipaddress,json,os,re,sys,time,urllib.error,urllib.parse,urllib.request,sqlite3
from dataclasses import asdict,dataclass
from pathlib import Path
from typing import Any
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from asset_factory.registry import PROVIDERS,ProviderSpec,resolve_provider
JOB_ID_RE=re.compile(r"job_[A-Za-z0-9_-]{12,40}\Z")
MAX_INPUT_BYTES=12*1024*1024
@dataclass(frozen=True)
class AssetResult:
    asset_type:str; provider:str; model:str; job_id:str; artifact_path:str; sha256:str; size_bytes:int; content_type:str; metadata_path:str; upload_queue_id:int=0

def _loopback(host:str)->bool:
    if host.lower()=="localhost": return True
    try: return ipaddress.ip_address(host).is_loopback
    except ValueError: return False

def service_base_url(spec:ProviderSpec,environ:dict[str,str]|None=None)->str:
    env=os.environ if environ is None else environ
    raw=env.get(spec.env_key,f"http://127.0.0.1:{spec.default_port}")
    if not isinstance(raw,str) or not raw or raw!=raw.strip(): raise ValueError(f"{spec.env_key} must be a loopback URL without surrounding whitespace")
    p=urllib.parse.urlsplit(raw)
    try: port=p.port
    except ValueError as exc: raise ValueError(f"{spec.env_key} has an invalid port") from exc
    if p.scheme!="http" or not p.hostname or not _loopback(p.hostname) or port!=spec.default_port or p.username or p.password or p.path not in ("","/") or p.query or p.fragment:
        raise ValueError(f"{spec.env_key} must be a root HTTP URL on loopback port {spec.default_port}")
    return f"http://{p.netloc}"

def _opener(url:str):
    host=urllib.parse.urlsplit(url).hostname or ""
    if not _loopback(host): raise ValueError("OEC sidecar requests must remain on loopback")
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))

def _json(url:str,method:str="GET",payload:dict[str,Any]|None=None,timeout:float=30)->dict[str,Any]:
    body=json.dumps(payload,ensure_ascii=False).encode("utf-8") if payload is not None else None
    req=urllib.request.Request(url,data=body,method=method,headers={"Accept":"application/json","Cache-Control":"no-store",**({"Content-Type":"application/json"} if body is not None else {})})
    try:
        with _opener(url).open(req,timeout=timeout) as response:
            if response.headers.get_content_type()!="application/json": raise RuntimeError("sidecar returned non-JSON response")
            raw=response.read(2*1024*1024+1)
    except urllib.error.HTTPError as exc: raise RuntimeError(f"sidecar HTTP {exc.code}: {exc.read(2048).decode('utf-8','replace')}") from exc
    if len(raw)>2*1024*1024: raise RuntimeError("sidecar JSON response exceeded 2 MiB")
    try: result=json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError,json.JSONDecodeError) as exc: raise RuntimeError("sidecar returned malformed JSON") from exc
    if not isinstance(result,dict): raise RuntimeError("sidecar JSON must be an object")
    return result

def _encode_input(value:str|Path,kind:str)->tuple[str,str]:
    path=Path(value).expanduser()
    if path.is_symlink() or not path.is_file(): raise ValueError(f"input {kind} must be a regular non-symlink file")
    from core_config import SYSTEM_DIRS
    allowed_roots = [
        Path(SYSTEM_DIRS["inputs"]).expanduser().resolve(),
        (Path(SYSTEM_DIRS["outputs"]).expanduser().resolve() / "asset_factory"),
    ]
    resolved = path.resolve()
    if not any(root != resolved and root in resolved.parents for root in allowed_roots):
        raise ValueError("input file must be under the OEC-managed inputs root or Asset Factory output root")
    path = resolved
    raw=path.read_bytes()
    if not raw or len(raw)>MAX_INPUT_BYTES: raise ValueError("input must be between 1 byte and 12 MiB")
    if kind=="image":
        valid=raw.startswith(b"\x89PNG\r\n\x1a\n") or raw.startswith(b"\xff\xd8\xff") or (len(raw)>=12 and raw[:4]==b"RIFF" and raw[8:12]==b"WEBP")
    else:
        valid=(len(raw)>=12 and raw[:4]==b"RIFF" and raw[8:12]==b"WAVE") or raw.startswith(b"fLaC") or raw.startswith(b"OggS") or raw.startswith(b"ID3") or (len(raw)>=2 and raw[0]==255 and (raw[1]&224)==224) or (len(raw)>=12 and raw[4:8]==b"ftyp")
    if not valid: raise ValueError(f"input file does not match an accepted {kind} container")
    return base64.b64encode(raw).decode("ascii"),path.name

def _managed_write(size:int):
    from storage_manager import managed_storage_operation
    return managed_storage_operation("outputs",required_gb=max(0.001,size/(1024**3)+0.01),require_fresh_quota=True,minimum_free_gb=0.02)

def _hash(path:Path)->str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda:f.read(1024*1024),b""): h.update(block)
    return h.hexdigest()

def _enqueue_hf_upload(asset_path:Path,metadata_path:Path)->int:
    """Put a completed artifact/manifest pair into OEC's existing HF upload queue."""
    from core_config import QUEUE_DB_PATH
    from storage_manager import managed_storage_operation
    if asset_path.is_symlink() or metadata_path.is_symlink() or not asset_path.is_file() or not metadata_path.is_file():
        raise FileNotFoundError("asset and metadata must be regular files before enqueue")
    asset_size=asset_path.stat().st_size
    metadata_size=metadata_path.stat().st_size
    if asset_size<1 or metadata_size<1:
        raise ValueError("empty asset or metadata cannot be queued")
    total_size=asset_size+metadata_size
    db_path=Path(QUEUE_DB_PATH).expanduser()
    with managed_storage_operation("outputs",required_gb=0.001,require_fresh_quota=True,minimum_free_gb=0.02):
        db_path.parent.mkdir(parents=True,exist_ok=True)
        with sqlite3.connect(str(db_path),timeout=30) as conn:
            conn.execute("PRAGMA busy_timeout=30000")
            # Match the extension-agnostic table contract used by hf_upload_daemon.AssetQueue.
            conn.execute("""CREATE TABLE IF NOT EXISTS assets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asset_path TEXT NOT NULL,
                json_path TEXT NOT NULL,
                total_size_bytes INTEGER NOT NULL,
                status TEXT DEFAULT 'PENDING',
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )""")
            cursor=conn.execute(
                "INSERT INTO assets (asset_path,json_path,total_size_bytes,status) VALUES (?,?,?,'PENDING')",
                (str(asset_path.resolve()),str(metadata_path.resolve()),total_size),
            )
            queue_id=cursor.lastrowid
            conn.commit()
            if not isinstance(queue_id,int) or queue_id<1:
                raise RuntimeError("upload queue did not return a valid row ID")
    return queue_id



class AssetFactoryClient:
    def __init__(self,*,timeout_seconds:int=1800,poll_seconds:float=2,output_root:str|Path|None=None):
        from core_config import SYSTEM_DIRS
        self.output_root=Path(output_root or (Path(SYSTEM_DIRS["outputs"])/"asset_factory")).expanduser().resolve()
        self.timeout_seconds=max(30,int(timeout_seconds)); self.poll_seconds=max(0.25,float(poll_seconds))
    def generate(self,asset_type:str,prompt:str,*,model:str|None=None,input_path:str|Path|None=None,parameters:dict[str,Any]|None=None,_child:bool=False)->list[AssetResult]:
        kind=asset_type.strip().lower().replace("-","_"); spec=resolve_provider(kind,model)
        if spec.input_required and input_path is None:
            if kind=="3d_asset" and spec.name=="trellis" and not _child:
                image=self.generate("image",prompt,model="flux",parameters={"width":512,"height":512})
                return image+self.generate("3d_asset",prompt,model="trellis",input_path=image[-1].artifact_path,parameters=parameters,_child=True)
            raise ValueError(f"{spec.name} requires an input {spec.input_kind} file")
        if spec.name in {"whisper","qwen3-asr"} and input_path is None: raise ValueError("ASR requires an existing audio file; text prompts cannot replace audio")
        if spec.name not in {"whisper","qwen3-asr"} and (not isinstance(prompt,str) or not prompt.strip()): raise ValueError("prompt must be non-empty")
        if len(prompt or "")>spec.max_prompt_chars: raise ValueError(f"prompt exceeds {spec.max_prompt_chars} characters for {spec.name}")
        params=dict(spec.default_parameters or {}); params.update(parameters or {})
        payload={"task":spec.task,"prompt":(prompt or "").strip(),"parameters":params}
        if spec.name=="ltx" and input_path is not None:
            encoded,filename=_encode_input(input_path,"image"); payload.update(task="image_to_video",image_base64=encoded,filename=filename)
        elif spec.input_kind:
            encoded,filename=_encode_input(input_path,spec.input_kind); payload.update({f"{spec.input_kind}_base64":encoded,"filename":filename})
        base=service_base_url(spec)
        submitted=_json(f"{base}/v1/jobs","POST",payload,30); job_id=submitted.get("job_id")
        if not isinstance(job_id,str) or not JOB_ID_RE.fullmatch(job_id): raise RuntimeError(f"{spec.name} returned invalid job ID")
        started=time.monotonic()
        while True:
            if time.monotonic()-started>self.timeout_seconds: raise TimeoutError(f"{spec.name} job {job_id} exceeded {self.timeout_seconds}s")
            state=_json(f"{base}/v1/jobs/{urllib.parse.quote(job_id,safe='')}",timeout=20)
            if state.get("job_id")!=job_id: raise RuntimeError("sidecar job ID did not match request")
            status=state.get("status")
            if status=="succeeded": break
            if status=="failed": raise RuntimeError(f"{spec.name} job failed: {str(state.get('message','failed'))[:500]}")
            if status not in {"queued","running"}: raise RuntimeError(f"unknown job state {status!r}")
            time.sleep(self.poll_seconds)
        return self._download(spec,base,job_id,kind,state)
    def _download(self,spec:ProviderSpec,base:str,job_id:str,kind:str,state:dict[str,Any])->list[AssetResult]:
        url=f"{base}/v1/jobs/{urllib.parse.quote(job_id,safe='')}/result"
        req=urllib.request.Request(url,headers={"Accept":spec.content_type,"Cache-Control":"no-store"})
        outdir=(self.output_root/kind).resolve()
        if self.output_root not in outdir.parents: raise ValueError("asset path escaped asset factory root")
        target=outdir/f"{job_id}.{spec.extension}"; metadata_path=target.with_suffix(target.suffix+".json")
        try: response=_opener(url).open(req,timeout=120)
        except urllib.error.HTTPError as exc: raise RuntimeError(f"{spec.name} result HTTP {exc.code}: {exc.read(2048).decode('utf-8','replace')}") from exc
        with response:
            content=response.headers.get_content_type()
            if content!=spec.content_type: raise RuntimeError(f"{spec.name} result MIME mismatch: {content}")
            try: length=int(response.headers.get("Content-Length",""))
            except ValueError as exc: raise RuntimeError("result Content-Length missing/invalid") from exc
            if length<1 or length>spec.max_result_bytes: raise RuntimeError("result is outside configured byte cap")
            outdir.mkdir(parents=True,exist_ok=True); digest=hashlib.sha256(); received=0
            try:
                with _managed_write(length),target.open("xb") as output:
                    while True:
                        chunk=response.read(1024*1024)
                        if not chunk: break
                        received+=len(chunk)
                        if received>length or received>spec.max_result_bytes: raise RuntimeError("result exceeded advertised size")
                        digest.update(chunk); output.write(chunk)
                    if received!=length: raise RuntimeError(f"truncated result: expected {length}, got {received}")
                    output.flush(); os.fsync(output.fileno())
                sha=digest.hexdigest()
                models={"flux":"black-forest-labs/FLUX.2-klein-4B","trellis":"microsoft/TRELLIS.2-4B","ltx":"Lightricks/LTX-2.3","ace-step":"ACE-Step-1.5","kokoro":"hexgrad/Kokoro-82M","whisper":"openai/whisper","qwen3-asr":"Qwen/Qwen3-ASR-0.6B","audiogen":"facebook/audiogen-medium","musicgen":"facebook/musicgen-medium"}
                manifest={"schema_version":1,"asset_type":kind,"provider":spec.name,"model":models[spec.name],"job_id":job_id,"artifact_path":str(target),"artifact_bytes":length,"artifact_sha256":sha,"content_type":content,"sidecar_metadata":state.get("metadata") if isinstance(state.get("metadata"),dict) else {},"created_at":state.get("created_at"),"completed_at":state.get("updated_at")}
                serialized=json.dumps(manifest,indent=2,sort_keys=True)+"\n"
                with _managed_write(len(serialized)+1024),metadata_path.open("x",encoding="utf-8") as output:
                    output.write(serialized); output.flush(); os.fsync(output.fileno())
                try:
                    upload_queue_id=_enqueue_hf_upload(target,metadata_path)
                except Exception as exc:
                    # Keep the valid artifact manifest immutable for recovery; queue state belongs in SQLite/status logs.
                    raise RuntimeError(f"asset was saved at {target} but HF upload enqueue failed; manifest={metadata_path}; cause={type(exc).__name__}") from exc
                return [AssetResult(kind,spec.name,models[spec.name],job_id,str(target),sha,length,content,str(metadata_path),upload_queue_id)]
            except BaseException:
                # Keep completed assets and manifests when queue admission fails; they are recovery evidence.
                if not metadata_path.exists():
                    target.unlink(missing_ok=True)
                raise

def main()->int:
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--asset-type",choices=("image","3d_asset","video","song","music","sound_effect","speech","tts","transcript"),required=True)
    p.add_argument("--model",choices=tuple(PROVIDERS)); p.add_argument("--prompt",default=""); p.add_argument("--input"); p.add_argument("--parameters-json",default="{}"); p.add_argument("--timeout-seconds",type=int,default=1800)
    a=p.parse_args()
    try:
        params=json.loads(a.parameters_json)
        if not isinstance(params,dict): raise ValueError("--parameters-json must encode an object")
        results=AssetFactoryClient(timeout_seconds=a.timeout_seconds).generate(a.asset_type,a.prompt,model=a.model,input_path=a.input,parameters=params)
        print(json.dumps([asdict(r) for r in results],indent=2,sort_keys=True)); return 0
    except Exception as exc:
        print(f"ASSET_FACTORY_ERROR={type(exc).__name__}: {exc}",file=sys.stderr); return 2
if __name__=="__main__": raise SystemExit(main())
