"""Provider-independent scientific contract models."""

from .mission import MissionSpec
from .research import ResearchObject, ResearchObjectKind

__all__ = ["MissionSpec", "ResearchObject", "ResearchObjectKind"]
