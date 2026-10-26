#!/usr/bin/env python3
"""Loopback JSON sidecar for FLUX.2 Klein text-to-image."""
from __future__ import annotations
import argparse,gc,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from core_config import SYSTEM_DIRS
from tools.media_services.common import MediaProvider,RequestError,serve
from tools.prepare_flux_cache import ensure_flux_cache
from tools.media_services.model_cache import RuntimeLock

class FluxProvider(MediaProvider):
    name="flux"; artifact_content_type="image/png"; artifact_extension="png"; max_prompt_chars=800
    def __init__(self,gpu:int|None=None,allow_download:bool=False):
        super().__init__(allow_download); self.gpu_index=gpu; self.module=None; self.torch=None; self.pipe=None; self.snapshot=None; self.gpu=None
        self.runtime_lock=RuntimeLock("flux-klein-4b"); self.lock_owned=False
    def validate_request(self,payload:dict)->dict:
        if payload.get("task")!="text_to_image": raise RequestError("task must be 'text_to_image'")
        prompt=payload.get("prompt","")
        if not isinstance(prompt,str) or not prompt.strip() or len(prompt)>800: raise RequestError("prompt must contain 1-800 characters")
        params=payload.get("parameters",{})
        if not isinstance(params,dict) or set(params)-{"width","height","steps","guidance_scale","seed"}: raise RequestError("unsupported FLUX parameters")
        p={"width":params.get("width",512),"height":params.get("height",512),"steps":params.get("steps",4),"guidance_scale":params.get("guidance_scale",1.0),"seed":params.get("seed",42)}
        for key in ("width","height","steps","seed"):
            if isinstance(p[key],bool) or not isinstance(p[key],int): raise RequestError(f"{key} must be an integer")
        if isinstance(p["guidance_scale"],bool) or not isinstance(p["guidance_scale"],(int,float)): raise RequestError("guidance_scale must be numeric")
        try: self.module._validate(prompt,p["width"],p["height"],p["steps"],float(p["guidance_scale"])) if self.module else None
        except ValueError as exc: raise RequestError(str(exc)) from exc
        if not 1<=p["steps"]<=20 or p["width"] not in {512,768,1024} or p["height"] not in {512,768,1024} or not 0<=float(p["guidance_scale"])<=10 or not 0<=p["seed"]<=2**31-1: raise RequestError("FLUX parameters are outside supported limits")
        return {"task":"text_to_image","prompt":prompt.strip(),"parameters":p}
    def load_runtime(self)->None:
        import pipeline_flux_image as module
        module._check_versions()
        self.gpu=module.select_idle_a100_gpu(self.gpu_index)
        self.runtime_lock.acquire()
        self.lock_owned=True
        self.snapshot=ensure_flux_cache(allow_download=self.allow_download)
        self.pipe,self.torch=module._load(self.snapshot,self.gpu); self.module=module
        self.model_name=module.MODEL_ID; self.model_revision=self.snapshot.name; self.device_name="cuda"; self.model_loaded=True
    def run_job(self,job_id:str,request:dict,input_file:Path|None):
        p=request["parameters"]; out=Path(SYSTEM_DIRS["outputs"]).expanduser().resolve()/"media_services"/"flux"/"jobs"/job_id/f"{job_id}.png"
        _image,meta=self.module._generate(self.pipe,self.torch,self.gpu,self.snapshot,request["prompt"],p["seed"],p["width"],p["height"],p["steps"],float(p["guidance_scale"]),out,False)
        return out,{"provider":"flux","model":self.model_name,"model_revision":self.model_revision,"task":"text_to_image","width":p["width"],"height":p["height"],"seed":p["seed"],"artifact_sha256":meta.get("artifact_sha256"),"generation_seconds":meta.get("generation_seconds")}
    def close(self)->None:
        self.model_loaded=False; self.pipe=None; self.torch=None; gc.collect()
        try:
            import torch
            if torch.cuda.is_available(): torch.cuda.empty_cache()
        except ImportError: pass
        if self.lock_owned:
            self.runtime_lock.release()
            self.lock_owned=False

def main()->int:
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--host",default="127.0.0.1"); p.add_argument("--port",type=int,default=7867); p.add_argument("--queue-size",type=int,default=1); p.add_argument("--timeout-seconds",type=int,default=900); p.add_argument("--gpu",type=int); p.add_argument("--allow-download",action="store_true",help="allow FLUX cache fill after fresh StorageManager admission")
    a=p.parse_args(); return serve(FluxProvider(a.gpu,a.allow_download),a.host,a.port,a.queue_size,a.timeout_seconds)
if __name__=="__main__": raise SystemExit(main())
