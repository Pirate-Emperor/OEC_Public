#!/usr/bin/env python3
"""Consume Brain's asset-factory queue independently of model runtimes."""
from __future__ import annotations
import argparse,json,os,signal,sys,time,uuid
from dataclasses import asdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from asset_factory.client import AssetFactoryClient
from core_config import SYSTEM_DIRS
from storage_manager import managed_storage_operation

def _write_json(path:Path,payload:dict)->None:
    with managed_storage_operation("outputs",required_gb=0.001,require_fresh_quota=True,minimum_free_gb=0.02):
        path.parent.mkdir(parents=True,exist_ok=True); temp=path.with_name(path.name+f".{uuid.uuid4().hex}.tmp")
        try:
            with temp.open("x",encoding="utf-8") as f: json.dump(payload,f,indent=2,sort_keys=True); f.write("\n"); f.flush(); os.fsync(f.fileno())
            os.replace(temp,path)
        finally: temp.unlink(missing_ok=True)

def process_one(path:Path,client:AssetFactoryClient,root:Path)->bool:
    if path.is_symlink() or not path.is_file(): return False
    claimed=path.with_name(path.name+f".processing-{os.getpid()}")
    try: os.replace(path,claimed)
    except OSError: return False
    try:
        job=json.loads(claimed.read_text(encoding="utf-8"))
        if not isinstance(job,dict) or not job.get("asset_factory"): raise ValueError("queue record is not an Asset Factory job")
        kind=job.get("asset_type"); prompt=job.get("prompt",""); model=job.get("model"); params=job.get("parameters",{})
        if not isinstance(params,dict): raise ValueError("parameters must be a JSON object")
        results=client.generate(kind,prompt,model=model,input_path=job.get("input_path"),parameters=params)
        state={"status":"succeeded","use_case":job.get("use_case"),"asset_type":kind,"results":[asdict(r) for r in results],"completed_at":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())}
        print("ASSET_FACTORY_JOB=PASS "+json.dumps(state,sort_keys=True),flush=True)
    except Exception as exc:
        state={"status":"failed","use_case":job.get("use_case") if isinstance(locals().get("job"),dict) else None,"error_type":type(exc).__name__,"error":str(exc)[:1000],"completed_at":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())}
        print("ASSET_FACTORY_JOB=FAIL "+json.dumps(state,sort_keys=True),file=sys.stderr,flush=True)
    _write_json(root/"status"/(path.stem+".status.json"),state)
    archive=root/"processed"/path.name; archive.parent.mkdir(parents=True,exist_ok=True); os.replace(claimed,archive)
    return True

def main()->int:
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--once",action="store_true"); p.add_argument("--poll-seconds",type=float,default=5); p.add_argument("--timeout-seconds",type=int,default=1800)
    a=p.parse_args(); root=Path(SYSTEM_DIRS["outputs"]).expanduser().resolve()/"asset_factory"; queue=root/"jobs"
    with managed_storage_operation("outputs",required_gb=0.001,require_fresh_quota=True,minimum_free_gb=0.02): queue.mkdir(parents=True,exist_ok=True)
    client=AssetFactoryClient(timeout_seconds=a.timeout_seconds); stopped=False
    def stop(_sig,_frame):
        nonlocal stopped; stopped=True
    signal.signal(signal.SIGINT,stop); signal.signal(signal.SIGTERM,stop)
    while not stopped:
        worked=False
        for item in sorted(queue.glob("job_*.json")):
            if process_one(item,client,root): worked=True; break
        if a.once: return 0 if worked else 3
        if not worked: time.sleep(max(0.5,a.poll_seconds))
    return 0
if __name__=="__main__": raise SystemExit(main())
