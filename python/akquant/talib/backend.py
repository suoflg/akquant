"""Backend selection for TA-Lib compatibility layer."""

import os

BackendKind = str
_SUPPORTED_BACKENDS = {"auto", "python", "rust"}


def resolve_backend(backend: str) -> BackendKind:
    """Resolve backend selection."""
    backend_key = str(backend).strip().lower()
    if backend_key not in _SUPPORTED_BACKENDS:
        supported = ", ".join(sorted(_SUPPORTED_BACKENDS))
        raise ValueError(f"backend must be one of: {supported}")
    if backend_key == "auto":
        env_backend = str(os.getenv("AKQUANT_TALIB_AUTO_BACKEND", "rust"))
        env_backend = env_backend.strip().lower()
        if env_backend in {"python", "rust"}:
            return env_backend
        return "rust"
    return backend_key


def ensure_rust_available(indicator_name: str) -> None:
    """Raise explicit error when rust backend is not implemented."""
    raise NotImplementedError(f"{indicator_name} is not available on rust backend yet")
