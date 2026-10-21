"""Typed multimodal OEC asset factory."""
from .registry import PROVIDERS, DEFAULT_PROVIDER_BY_ASSET, resolve_provider
__all__ = ["PROVIDERS", "DEFAULT_PROVIDER_BY_ASSET", "resolve_provider"]
