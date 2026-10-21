#!/usr/bin/env python3
"""Loopback JSON sidecar for AudioGen sound effects and MusicGen music."""
from __future__ import annotations
import argparse,gc,os,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from core_config import SYSTEM_DIRS
from tools.media_services.common import MediaProvider,RequestError,managed_write,serve

class AudioCraftProvider(MediaProvider):
    artifact_content_type="audio/wav"; artifact_extension="wav"; max_prompt_chars=1200
    def __init__(self,model:str,allow_download:bool=False,gpu:int|None=None,license_accepted:bool=False):
        super().__init__(allow_download)
        if model not in {"audiogen","musicgen"}: raise ValueError("model must be audiogen or musicgen")
        self.name=model; self.kind=model; self.gpu_index=gpu; self.license_accepted=license_accepted; self.runtime=None; self.torch=None; self.module=None; self.snapshot=None
        self.model_name={"audiogen":"facebook/audiogen-medium","musicgen":"facebook/musicgen-medium"}[model]
    def validate_request(self,payload:dict)->dict:
        task="text_to_audio" if self.kind=="audiogen" else "text_to_music"
        if payload.get("task")!=task: raise RequestError(f"task must be {task!r}")
        prompt=payload.get("prompt","")
        if not isinstance(prompt,str) or not prompt.strip() or len(prompt)>1200: raise RequestError("prompt must contain 1-1200 characters")
        params=payload.get("parameters",{})
        if not isinstance(params,dict) or set(params)-{"duration_seconds","seed"}: raise RequestError("unsupported AudioCraft parameters")
        duration=params.get("duration_seconds",3 if self.kind=="audiogen" else 8); seed=params.get("seed",42)
        if isinstance(duration,bool) or not isinstance(duration,int) or not 1<=duration<=10: raise RequestError("duration_seconds must be an integer from 1 to 10")
        if isinstance(seed,bool) or not isinstance(seed,int) or not 0<=seed<=2**31-1: raise RequestError("seed must be a non-negative 32-bit integer")
        return {"task":task,"prompt":prompt.strip(),"parameters":{"duration_seconds":duration,"seed":seed}}
    def load_runtime(self)->None:
        if not self.license_accepted: raise RuntimeError("AudioCraft license/use boundary not acknowledged; pass --accept-noncommercial-license only for permitted use")
        self.module=__import__("pipeline_audiogen" if self.kind=="audiogen" else "pipeline_musicgen",fromlist=["*"])
        self.packages=self.module._check_versions()
        self.gpu=self.module._select_gpu(self.gpu_index) if self.kind=="audiogen" else self.module._gpu(self.gpu_index)
        os.environ["CUDA_VISIBLE_DEVICES"]=self.gpu["index"]; os.environ["AUDIOCRAFT_CACHE_DIR"]=str(Path(SYSTEM_DIRS["models"]).expanduser().resolve())
        self.snapshot=self.module._snapshot(self.allow_download)
        import torch
        if not torch.cuda.is_available(): raise RuntimeError("CUDA unavailable after A100 selection")
        torch.cuda.set_device(0)
        if "A100" not in torch.cuda.get_device_name(0).upper(): raise RuntimeError("visible device is not an A100")
        if self.kind=="audiogen":
            from audiocraft.models import AudioGen
            self.runtime=AudioGen.get_pretrained(self.model_name,device="cuda")
        else:
            from audiocraft.models import MusicGen
            self.runtime=MusicGen.get_pretrained(self.model_name,device="cuda")
        self.torch=torch; self.model_revision=self.snapshot.name; self.device_name="cuda"; self.model_loaded=True
    def run_job(self,job_id:str,request:dict,input_file:Path|None):
        import soundfile as sf
        p=request["parameters"]; self.runtime.set_generation_params(duration=int(p["duration_seconds"]))
        self.torch.manual_seed(int(p["seed"])); self.torch.cuda.manual_seed_all(int(p["seed"])); self.torch.cuda.reset_peak_memory_stats(); start=time.monotonic()
        with self.torch.inference_mode(): waveform=self.runtime.generate([request["prompt"]])
        elapsed=time.monotonic()-start; outdir=Path(SYSTEM_DIRS["outputs"]).expanduser().resolve()/"media_services"/self.name/"jobs"/job_id
        outdir.mkdir(parents=True,exist_ok=True); target=outdir/f"{job_id}.wav"
        with managed_write("outputs",max(.03,p["duration_seconds"]*.01),minimum_free_gb=.02):
            sf.write(str(target),waveform[0].detach().float().cpu().transpose(0,1).numpy(),int(self.runtime.sample_rate),subtype="PCM_16",format="WAV")
        if not target.is_file() or target.stat().st_size<64: raise RuntimeError("AudioCraft returned an empty WAV")
        return target,{"provider":self.kind,"model":self.model_name,"model_revision":self.model_revision,"physical_gpu":int(self.gpu["index"]),"prompt":request["prompt"],"seed":p["seed"],"duration_seconds":p["duration_seconds"],"sample_rate":int(self.runtime.sample_rate),"generation_seconds":round(elapsed,3),"peak_allocated_gib":round(self.torch.cuda.max_memory_allocated()/1024**3,3),"peak_reserved_gib":round(self.torch.cuda.max_memory_reserved()/1024**3,3),"license":"CC-BY-NC-4.0","use_boundary":"non-commercial use only unless licensing terms are independently confirmed","packages":self.packages}
    def close(self)->None:
        self.model_loaded=False; self.runtime=None; self.torch=None; gc.collect()
        try:
            import torch
            if torch.cuda.is_available(): torch.cuda.empty_cache()
        except ImportError: pass

def main()->int:
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--model",choices=("audiogen","musicgen"),required=True); p.add_argument("--host",default="127.0.0.1"); p.add_argument("--port",type=int); p.add_argument("--queue-size",type=int,default=1); p.add_argument("--timeout-seconds",type=int,default=900); p.add_argument("--gpu",type=int); p.add_argument("--allow-download",action="store_true"); p.add_argument("--accept-noncommercial-license",action="store_true",help="Acknowledge AudioCraft checkpoint's non-commercial license boundary")
    a=p.parse_args(); port=a.port or (7874 if a.model=="audiogen" else 7875)
    return serve(AudioCraftProvider(a.model,a.allow_download,a.gpu,a.accept_noncommercial_license),a.host,port,a.queue_size,a.timeout_seconds)
if __name__=="__main__": raise SystemExit(main())
