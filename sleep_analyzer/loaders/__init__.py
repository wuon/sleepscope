from __future__ import annotations

from sleep_analyzer.loaders.base import (
    SessionLoader,
    clear_registry,
    get_loader,
    register_loader,
    registered_providers,
)

# Import concrete loaders for side-effect registration.
from sleep_analyzer.loaders import fitbit as _fitbit  # noqa: F401
from sleep_analyzer.loaders import sleepscope as _sleepscope  # noqa: F401

__all__ = [
    "SessionLoader",
    "clear_registry",
    "get_loader",
    "register_loader",
    "registered_providers",
]
