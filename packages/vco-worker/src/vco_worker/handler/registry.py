"""Handler registry -- maps handler type names to handler classes.

Lazy imports to avoid circular dependencies. Handler classes are imported
on first access, not at module load time.
"""

from __future__ import annotations

from typing import Any

_HANDLER_REGISTRY: dict[str, str] = {
    "session": "vco_worker.handler.session:GsdSessionHandler",
    "conversation": "vco_worker.handler.conversation:WorkerConversationHandler",
    "transient": "vco_worker.handler.transient:PMTransientHandler",
}


def get_handler(handler_type: str) -> Any:
    """Get handler instance by type name.

    Uses lazy import from dotted path to avoid circular imports.
    Raises ValueError if handler_type is not registered.
    """
    dotted = _HANDLER_REGISTRY.get(handler_type)
    if dotted is None:
        raise ValueError(
            f"Unknown handler type: {handler_type!r}. Valid: {list(_HANDLER_REGISTRY)}"
        )
    module_path, class_name = dotted.rsplit(":", 1)
    import importlib

    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)
    return cls()
