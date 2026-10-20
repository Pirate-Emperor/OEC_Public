#!/usr/bin/env python3
"""Read-only OEC media-service readiness report for downstream integrations.

Never starts/stops services, installs packages, downloads weights, allocates a GPU,
or purges caches. HTTP API usability requires /health HTTP 200, ready=true and
model_loaded=true. AudioGen/MusicGen are reported separately as CLI-only.
"""
from __future__ import annotations
import argparse, importlib.util, json, os, subprocess, sys, urllib.error, urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

SPECS: dict[str, dict[str, Any]] = {
    "ltx": {"display_name":"LTX-2.3 video generation","port":17869,"env":"phase1_ltx",
            "python_kind":"conda","modules":["torch","diffusers","transformers","safetensors"],
            "repo":"Lightricks/LTX-2.3","artifact":"video/mp4","operation":"text_to_video|image_to_video"},
    "trellis": {"display_name":"TRELLIS.2 image-to-3D","port":17868,"env":"phase2_3d",
            "python_kind":"conda","modules":["torch","o_voxel","trimesh","PIL"],
            "repo":"microsoft/TRELLIS.2-4B","artifact":"model/gltf-binary (GLB)","operation":"image_to_3d"},
    "ace-step": {"display_name":"ACE-Step 1.5 music generation","port":7870,"env":"oec-acestep-py311",
            "python_kind":"venv","modules":["torch","acestep"],"artifact":"audio/flac","operation":"text_to_music"},
    "kokoro": {"display_name":"Kokoro-82M text-to-speech","port":7871,"env":"oec-audio-py311",
            "python_kind":"venv","modules":["torch","kokoro"],"repo":"hexgrad/Kokoro-82M",
            "artifact":"audio/wav","operation":"text_to_speech"},
    "whisper": {"display_name":"OpenAI Whisper Turbo speech recognition","port":7872,"env":"oec-audio-py311",
            "python_kind":"venv","modules":["torch","whisper"],"checkpoint":"whisper/turbo/large-v3-turbo.pt",
            "artifact":"text/plain","operation":"transcribe"},
    "qwen3-asr": {"display_name":"Qwen3-ASR-0.6B speech recognition","port":7873,"env":"oec-audio-py311",
            "python_kind":"venv","modules":["torch","qwen_asr"],"repo":"Qwen/Qwen3-ASR-0.6B",
            "artifact":"text/plain","operation":"transcribe"},
    "audiogen": {"display_name":"AudioGen medium sound effects","port":None,"env":"phase1",
            "python_kind":"conda","modules":["torch","audiocraft","soundfile"],"repo":"facebook/audiogen-medium",
            "artifact":"audio/wav","operation":"CLI/Gradio only; no supervised OEC HTTP job API is implemented"},
    "musicgen": {"display_name":"MusicGen medium music generation","port":None,"env":"phase1",
            "python_kind":"conda","modules":["torch","audiocraft","soundfile"],"repo":"facebook/musicgen-medium",
            "artifact":"audio/wav","operation":"CLI/Gradio only; no supervised OEC HTTP job API is implemented"},
}
PATH_KEYS={"AIEROS_BASE_DIR","AIEROS_MODELS_DIR","AIEROS_CACHE_DIR","CONDA_ROOT"}

def _paths() -> dict[str, Path]:
    home=Path.home()
    values={k:v for k,v in os.environ.items() if k in PATH_KEYS and v}
    try:
        for line in (home/".env").read_text(encoding="utf-8").splitlines():
            line=line.strip()
            if not line or line.startswith("#") or "=" not in line: continue
            k,v=line.split("=",1); k=k.strip()
            if k in PATH_KEYS and k not in values: values[k]=v.strip().strip("'").strip('"')
    except OSError: pass
    def resolve(key: str, fallback: Path) -> Path:
        return Path(os.path.expandvars(os.path.expanduser(values.get(key,str(fallback))))).resolve()
    base=resolve("AIEROS_BASE_DIR",home)
    return {"home":home,"models":resolve("AIEROS_MODELS_DIR",base/"aireos_models"),
            "cache":resolve("AIEROS_CACHE_DIR",base/"aireos_cache"),
            "conda":resolve("CONDA_ROOT",home/"Conda")}

def _python_for(spec: dict[str, Any], paths: dict[str, Path]) -> Path:
    if spec["python_kind"]=="venv":
        return paths["home"]/".local"/"venvs"/spec["env"]/"bin"/"python"
    return paths["conda"]/"envs"/spec["env"]/"bin"/"python"

def _probe_health(port: int) -> dict[str, Any]:
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    request=urllib.request.Request(f"http://127.0.0.1:{port}/health",headers={"Accept":"application/json"})
    try:
        with opener.open(request,timeout=2.5) as response:
            data=json.loads(response.read(65536).decode("utf-8"))
            return _health_fields(response.status,data)
    except urllib.error.HTTPError as exc:
        try: data=json.loads(exc.read(65536).decode("utf-8"))
        except Exception: data={}
        return _health_fields(exc.code,data)
    except Exception as exc:
        return {"reachable":False,"http_status":None,"error_type":type(exc).__name__}

def _health_fields(status: int,data: dict[str,Any]) -> dict[str,Any]:
    return {"reachable":True,"http_status":status,"ready":data.get("ready") is True,
            "model_loaded":data.get("model_loaded") is True,"loading":data.get("loading") is True,
            "storage_ready":data.get("storage_ready"),"message":data.get("message"),"error":data.get("error")}

def _check_modules(python: Path, modules: list[str]) -> dict[str,Any]:
    if not python.is_file():
        return {"interpreter_exists":False,"interpreter":str(python),"modules":{m:False for m in modules}}
    code=("import importlib.util,json; names="+repr(modules)+"; "
          "print(json.dumps({n: importlib.util.find_spec(n) is not None for n in names}))")
    try:
        result=subprocess.run([str(python),"-c",code],capture_output=True,text=True,timeout=15,
                              check=False,env={**os.environ,"PYTHONDONTWRITEBYTECODE":"1"})
        data=json.loads(result.stdout.strip().splitlines()[-1]) if result.stdout.strip() else {}
        return {"interpreter_exists":True,"interpreter":str(python),"python_exit_code":result.returncode,
                "modules":{m:data.get(m) is True for m in modules},
                "probe_error_type":"ModuleProbeFailed" if result.returncode else None}
    except subprocess.TimeoutExpired:
        return {"interpreter_exists":True,"interpreter":str(python),"modules":{m:False for m in modules},
                "probe_error_type":"TimeoutExpired"}
    except (OSError,ValueError,json.JSONDecodeError) as exc:
        return {"interpreter_exists":True,"interpreter":str(python),"modules":{m:False for m in modules},
                "probe_error_type":type(exc).__name__}

def _hf_cache_has_weights(models: Path,repo_id: str) -> bool:
    slug="models--"+repo_id.replace("/","--")
    for parent in (models/"hub",models):
        repo=parent/slug; snaps=repo/"snapshots"
        if repo.is_symlink() or not snaps.is_dir() or snaps.is_symlink(): continue
        try: snapshot_dirs=list(snaps.iterdir())
        except OSError: continue
        for snapshot in snapshot_dirs:
            if snapshot.is_symlink() or not snapshot.is_dir(): continue
            for folder,dirs,files in os.walk(snapshot,followlinks=False):
                base=Path(folder); dirs[:]=[d for d in dirs if not (base/d).is_symlink()]
                for filename in files:
                    item=base/filename
                    if item.suffix.lower() not in {".safetensors",".bin",".pt",".pth"}: continue
                    try:
                        resolved=item.resolve(strict=True)
                        if repo.resolve() in resolved.parents and resolved.is_file() and resolved.stat().st_size>1024*1024:
                            return True
                    except OSError: continue
    return False

def _cache_status(name: str,spec: dict[str,Any],paths: dict[str,Path]) -> dict[str,Any]:
    if "repo" in spec:
        found=_hf_cache_has_weights(paths["models"],spec["repo"])
        return {"checkpoint_presence":"PRESENT" if found else "MISSING_OR_INCOMPLETE",
                "some_real_weights_detected":found}
    if name=="whisper":
        checkpoint=paths["models"]/spec["checkpoint"]
        try: found=checkpoint.is_file() and not checkpoint.is_symlink() and checkpoint.stat().st_size>=1_000_000_000
        except OSError: found=False
        return {"checkpoint_presence":"PRESENT" if found else "MISSING_OR_INCOMPLETE",
                "checkpoint_path":str(checkpoint),"some_real_weights_detected":found}
    if name=="ace-step":
        model=paths["models"]/"ace-step-1.5"
        try:
            from prepare_ace_step_runtime import checkpoint_component_complete,selected_main_components_complete
            main_ok=selected_main_components_complete(model)
            lm_ok=checkpoint_component_complete(model/"acestep-5Hz-lm-0.6B","acestep-5Hz-lm-0.6B")
            source=paths["cache"]/"third_party"/"ACE-Step-1.5"
            return {"checkpoint_presence":"COMPLETE" if main_ok and lm_ok else "MISSING_OR_INCOMPLETE",
                    "main_components_complete":main_ok,"lm_0_6b_complete":lm_ok,
                    "source_checkout_present":source.is_dir() and not source.is_symlink()}
        except Exception as exc:
            return {"checkpoint_presence":"UNKNOWN","probe_error_type":type(exc).__name__}
    return {"checkpoint_presence":"NOT_CHECKED"}

def assess_service(name: str,*,paths:dict[str,Path]|None=None,
                   probe:Callable[[int],dict[str,Any]]=_probe_health,
                   module_check:Callable[[Path,list[str]],dict[str,Any]]=_check_modules,
                   cache_check:Callable[[str,dict[str,Any],dict[str,Path]],dict[str,Any]]=_cache_status)->dict[str,Any]:
    spec=SPECS[name]; paths=paths or _paths(); python=_python_for(spec,paths)
    runtime=module_check(python,spec["modules"]); cache=cache_check(name,spec,paths)
    if spec["port"] is None:
        api_status="NOT_EXPOSED"; health=None; usable=False
    else:
        health=probe(spec["port"])
        usable=(health.get("http_status")==200 and health.get("ready") is True and health.get("model_loaded") is True)
        api_status="READY" if usable else ("NOT_READY" if health.get("reachable") else "UNREACHABLE")
    runtime_ok=(runtime.get("interpreter_exists") is True and runtime.get("python_exit_code",0)==0
                and all(runtime.get("modules",{}).get(m) is True for m in spec["modules"])
                and cache.get("checkpoint_presence") not in {"MISSING_OR_INCOMPLETE","UNKNOWN"})
    if name=="ace-step": runtime_ok=runtime_ok and cache.get("source_checkout_present") is True
    return {"provider":name,"display_name":spec["display_name"],"api_status":api_status,
            "usable_by_deploy_now":usable,"endpoint":f"http://127.0.0.1:{spec['port']}" if spec["port"] else None,
            "health":health,"expected_environment":spec["env"],"runtime_preflight":"PASS" if runtime_ok else "BLOCKED_OR_INCOMPLETE",
            "python":str(python),"module_check":runtime,"cache":cache,"operation":spec["operation"],
            "artifact_type":spec["artifact"],
            "remote_access":"loopback-only; use an SSH tunnel from the deployment host; do not expose the port publicly"
                           if spec["port"] else "not available as a supervised OEC HTTP job API"}

def build_report() -> dict[str,Any]:
    paths=_paths(); rows=[assess_service(n,paths=paths) for n in SPECS]
    return {"schema_version":1,"timestamp_utc":datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "report_type":"read_only","side_effects":{"starts_services":False,"installs_packages":False,
            "downloads_weights":False,"allocates_gpu":False,"purges_cache":False,"reads_reserve_file_directly":False},
            "models_root":str(paths["models"]),"services":rows,
            "deployment_contract":{"ready_condition":"api_status == READY; /health must be HTTP 200 with ready=true and model_loaded=true",
            "job_contract":"POST /v1/jobs -> 202/job_id; GET /v1/jobs/{job_id} until succeeded/failed; GET /v1/jobs/{job_id}/result to retrieve the validated artifact",
            "network":"Services bind to loopback. For OEC-Deploy on another host, forward each required port over SSH and configure its provider URL to the forwarded endpoint.",
            "not_yet_exposed":["audiogen","musicgen"]}}

def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json",action="store_true",help="Emit machine-readable JSON.")
    parser.add_argument("--provider",choices=tuple(SPECS),help="Restrict to one provider.")
    parser.add_argument("--strict",action="store_true",help="Exit non-zero unless selected APIs are READY and runtime preflight is PASS.")
    args=parser.parse_args(); report=build_report()
    rows=[r for r in report["services"] if args.provider is None or r["provider"]==args.provider]
    report["services"]=rows
    if args.json: print(json.dumps(report,indent=2,sort_keys=True,ensure_ascii=False))
    else:
        print("OEC MEDIA SERVICE READINESS (read-only; no service start/download/install/GPU/purge)")
        for row in rows:
            print(f"{row['provider']:10} api={row['api_status']:12} runtime={row['runtime_preflight']:22} "
                  f"env={row['expected_environment']} endpoint={row['endpoint'] or 'not exposed'}")
            missing=[m for m,v in row["module_check"].get("modules",{}).items() if not v]
            if missing: print("  missing modules: "+", ".join(missing))
            if row["api_status"]=="NOT_READY": print(f"  health={row['health']}")
            if row["cache"].get("checkpoint_presence") not in {"COMPLETE","PRESENT"}:
                print("  cache: "+str(row["cache"].get("checkpoint_presence")))
    if args.strict and any(r["api_status"]!="READY" or r["runtime_preflight"]!="PASS" for r in rows): return 1
    return 0

if __name__=="__main__":
    raise SystemExit(main())
