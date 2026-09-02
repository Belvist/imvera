"""IMVERA Product Core package (ROADMAP Э4)."""

__all__ = ["create_app", "main"]


def __getattr__(name):
    if name in ("create_app", "main"):
        from product.api import create_app, main
        return create_app if name == "create_app" else main
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
