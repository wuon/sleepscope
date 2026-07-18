from __future__ import annotations

from pathlib import Path
from typing import Protocol

from sleep_analyzer.models import BinarySession


class SessionLoader(Protocol):
    name: str

    def load(self, path: Path) -> BinarySession:
        """Load a provider export into a binary Sleep/Awake session."""


_REGISTRY: dict[str, SessionLoader] = {}


def register_loader(loader: SessionLoader) -> SessionLoader:
    _REGISTRY[loader.name] = loader
    return loader


def get_loader(provider: str) -> SessionLoader:
    key = provider.strip().lower()
    try:
        return _REGISTRY[key]
    except KeyError as exc:
        known = ", ".join(sorted(_REGISTRY)) or "(none)"
        raise KeyError(
            f"Unknown provider '{provider}'. Registered loaders: {known}. "
            "Add a loader and register it to support this provider."
        ) from exc


def registered_providers() -> tuple[str, ...]:
    return tuple(sorted(_REGISTRY))


def clear_registry() -> None:
    """Test helper to reset the loader registry."""
    _REGISTRY.clear()
