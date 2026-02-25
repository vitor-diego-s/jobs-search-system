"""Abstract base class for platform adapters."""

from abc import ABC, abstractmethod

from src.core.config import SearchConfig
from src.core.schemas import JobCandidate


class PlatformAdapter(ABC):
    """Base class that every platform adapter must implement."""

    @property
    @abstractmethod
    def platform_id(self) -> str:
        """Unique identifier for this platform (e.g. 'linkedin')."""

    @abstractmethod
    async def search(self, config: SearchConfig) -> list[JobCandidate]:
        """Run a search and return raw (unfiltered, unscored) candidates."""
