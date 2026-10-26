"""Public API, with the provider-dependent agent imported only on demand."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .agent import TraceableDeepResearcher

__all__ = ['TraceableDeepResearcher']


def __getattr__(name: str):
    if name == "TraceableDeepResearcher":
        from .agent import TraceableDeepResearcher

        globals()[name] = TraceableDeepResearcher
        return TraceableDeepResearcher
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
