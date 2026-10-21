import unittest
from asset_factory.registry import PROVIDERS,resolve_provider
from asset_factory.client import service_base_url
from tools.media_services.flux_api import FluxProvider
from tools.media_services.audiocraft_api import AudioCraftProvider

class AssetFactoryContractTests(unittest.TestCase):
 def test_nine_models_are_registered(self):
  self.assertEqual(set(PROVIDERS),{"flux","trellis","ltx","ace-step","kokoro","whisper","qwen3-asr","audiogen","musicgen"})
 def test_asset_kind_defaults(self):
  expected={"image":"flux","3d_asset":"trellis","video":"ltx","song":"ace-step","music":"musicgen","sound_effect":"audiogen","speech":"kokoro","tts":"kokoro","transcript":"whisper"}
  for kind,name in expected.items(): self.assertEqual(resolve_provider(kind).name,name)
 def test_wrong_asset_model_pair_fails(self):
  with self.assertRaises(ValueError): resolve_provider("image","whisper")
  with self.assertRaises(ValueError): resolve_provider("sound_effect","musicgen")
 def test_fixed_loopback_urls(self):
  spec=PROVIDERS["flux"]; self.assertEqual(service_base_url(spec,{}),"http://127.0.0.1:7867")
  for value in ("https://127.0.0.1:7867","http://8.8.8.8:7867","http://127.0.0.1:9999","http://127.0.0.1:7867/v1"):
   with self.assertRaises(ValueError): service_base_url(spec,{spec.env_key:value})
 def test_flux_request_validation(self):
  p=FluxProvider()
  with self.assertRaises(Exception): p.validate_request({"task":"text_to_audio","prompt":"abc"})
  with self.assertRaises(Exception): p.validate_request({"task":"text_to_image","prompt":"x"*900})
  with self.assertRaises(Exception): p.validate_request({"task":"text_to_image","prompt":"valid","parameters":{"unknown":1}})
 def test_audiocraft_validation(self):
  p=AudioCraftProvider("audiogen")
  self.assertEqual(p.validate_request({"task":"text_to_audio","prompt":"Rain","parameters":{"duration_seconds":3}})["parameters"]["duration_seconds"],3)
  for body in ({"task":"text_to_audio","prompt":"Rain","parameters":{"duration_seconds":30}},{"task":"text_to_audio","prompt":"Rain","parameters":{"bad":1}}):
   with self.assertRaises(Exception): p.validate_request(body)
 def test_transcription_is_audio_input_driven(self):
  self.assertTrue(resolve_provider("transcript","whisper").input_required)
  self.assertEqual(resolve_provider("transcript","qwen3-asr").input_kind,"audio")
if __name__=="__main__": unittest.main()
