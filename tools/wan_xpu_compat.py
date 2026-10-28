"""Compatibility helper for optional torch.xpu APIs probed by Diffusers.

OEC's Wan notebook runs on CUDA/A100. Some pinned PyTorch builds expose an
incomplete optional XPU namespace; fill missing unavailable-backend hooks
without replacing a real available XPU implementation.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any


def ensure_torch_xpu_compat(torch_module: Any) -> Any:
    """Ensure Diffusers' optional XPU probes can run on a CUDA-only build."""
    xpu = getattr(torch_module, "xpu", None)
    if xpu is None:
        xpu = SimpleNamespace()

    availability = getattr(xpu, "is_available", None)
    if callable(availability):
        try:
            available = bool(availability())
        except Exception as exc:
            raise RuntimeError("torch.xpu.is_available() failed; refusing to mask the backend error") from exc
    else:
        available = False
        try:
            setattr(xpu, "is_available", lambda: False)
        except Exception as exc:
            raise RuntimeError("cannot add the missing torch.xpu.is_available hook") from exc

    for name, fallback in (
        ("device_count", lambda: 0),
        ("empty_cache", lambda: None),
    ):
        if callable(getattr(xpu, name, None)):
            continue
        if available:
            raise RuntimeError(
                f"torch.xpu reports an available backend but is missing {name}(); "
                "refusing to pretend the live backend is unavailable"
            )
        try:
            setattr(xpu, name, fallback)
        except Exception as exc:
            raise RuntimeError(f"cannot add the missing unavailable-XPU {name} hook") from exc

    try:
        setattr(torch_module, "xpu", xpu)
    except Exception as exc:
        if getattr(torch_module, "xpu", None) is not xpu:
            raise RuntimeError("cannot install the optional torch.xpu compatibility namespace") from exc
    return xpu
