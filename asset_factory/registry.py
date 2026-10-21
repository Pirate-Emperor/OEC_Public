"""Single registry for OEC asset kinds and model sidecar contracts."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class ProviderSpec:
    name: str
    asset_types: tuple[str, ...]
    env_key: str
    default_port: int
    task: str
    extension: str
    content_type: str
    input_kind: str | None = None
    input_required: bool = False
    image_optional: bool = False
    max_prompt_chars: int = 800
    max_result_bytes: int = 64 * 1024 * 1024
    default_parameters: dict[str, Any] | None = None

PROVIDERS: dict[str, ProviderSpec] = {
    "flux": ProviderSpec("flux",("image",),"OEC_FLUX_SERVICE_URL",7867,"text_to_image","png","image/png",max_prompt_chars=800,max_result_bytes=64*1024*1024,default_parameters={"width":512,"height":512,"steps":4,"guidance_scale":1.0,"seed":42}),
    "trellis": ProviderSpec("trellis",("3d_asset",),"OEC_TRELLIS_SERVICE_URL",7868,"image_to_3d","glb","model/gltf-binary",input_kind="image",input_required=True,max_prompt_chars=500,max_result_bytes=2*1024*1024*1024,default_parameters={"max_image_size":1024,"texture_size":2048,"decimation_target":100000}),
    "ltx": ProviderSpec("ltx",("video",),"OEC_LTX_SERVICE_URL",7869,"text_to_video","mp4","video/mp4",image_optional=True,max_prompt_chars=800,max_result_bytes=1024*1024*1024,default_parameters={"duration_seconds":4,"fps":24}),
    "ace-step": ProviderSpec("ace-step",("song",),"OEC_ACE_STEP_SERVICE_URL",7870,"text_to_music","flac","audio/flac",max_prompt_chars=512,max_result_bytes=1024*1024*1024,default_parameters={"duration_seconds":30,"seed":-1,"steps":8,"lyrics":"","instrumental":True,"language":"unknown"}),
    "kokoro": ProviderSpec("kokoro",("speech","tts"),"OEC_KOKORO_SERVICE_URL",7871,"text_to_speech","wav","audio/wav",max_prompt_chars=2500,max_result_bytes=128*1024*1024,default_parameters={"voice":"af_heart"}),
    "whisper": ProviderSpec("whisper",("transcript",),"OEC_WHISPER_SERVICE_URL",7872,"transcribe","txt","text/plain",input_kind="audio",input_required=True,max_prompt_chars=500,max_result_bytes=512*1024,default_parameters={"temperature":0.0,"condition_on_previous_text":True}),
    "qwen3-asr": ProviderSpec("qwen3-asr",("transcript",),"OEC_QWEN3_ASR_SERVICE_URL",7873,"transcribe","txt","text/plain",input_kind="audio",input_required=True,max_prompt_chars=500,max_result_bytes=512*1024,default_parameters={}),
    "audiogen": ProviderSpec("audiogen",("sound_effect",),"OEC_AUDIOGEN_SERVICE_URL",7874,"text_to_audio","wav","audio/wav",max_prompt_chars=1200,max_result_bytes=128*1024*1024,default_parameters={"duration_seconds":3,"seed":42}),
    "musicgen": ProviderSpec("musicgen",("music",),"OEC_MUSICGEN_SERVICE_URL",7875,"text_to_music","wav","audio/wav",max_prompt_chars=1200,max_result_bytes=512*1024*1024,default_parameters={"duration_seconds":8,"seed":42}),
}
DEFAULT_PROVIDER_BY_ASSET={"image":"flux","3d_asset":"trellis","video":"ltx","song":"ace-step","music":"musicgen","sound_effect":"audiogen","speech":"kokoro","tts":"kokoro","transcript":"whisper"}

def resolve_provider(asset_type: str, model: str | None = None) -> ProviderSpec:
    if not isinstance(asset_type,str) or not asset_type.strip(): raise ValueError("asset_type must be a non-empty string")
    normalized=asset_type.strip().lower().replace("-","_")
    provider=(model or DEFAULT_PROVIDER_BY_ASSET.get(normalized,"")).strip().lower()
    if not provider: raise ValueError(f"no default model is configured for asset_type={normalized!r}")
    spec=PROVIDERS.get(provider)
    if spec is None: raise ValueError(f"unsupported provider {provider!r}; choose one of {', '.join(PROVIDERS)}")
    if normalized not in spec.asset_types: raise ValueError(f"provider {provider!r} cannot produce asset_type={normalized!r}")
    return spec
