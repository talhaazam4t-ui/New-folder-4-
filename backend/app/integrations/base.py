"""Base Integration Adapter Contract for External Providers.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict


class BaseIntegrationAdapter(ABC):
    """Standard interface for third-party tenant integrations (WhatsApp, Email, Calendar, Payment)."""

    provider_name: str = "base"
    integration_type: str = "generic"

    @abstractmethod
    async def health_check(self) -> Dict[str, Any]:
        """Check connectivity with the external provider."""
        raise NotImplementedError
