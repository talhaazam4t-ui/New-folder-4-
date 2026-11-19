"""Tenant Context & Execution Scope Definition.

Encapsulates the verified tenant and user identity for every authenticated request.
"""

import uuid
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class TenantContext:
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    role: str
    status: str
    email: Optional[str] = None
    full_name: Optional[str] = None

    @property
    def is_owner(self) -> bool:
        return self.role in ("owner", "super_admin")

    @property
    def is_admin(self) -> bool:
        return self.role in ("owner", "admin", "super_admin")

    @property
    def can_manage(self) -> bool:
        return self.role in ("owner", "admin", "manager", "super_admin")

    @property
    def can_write(self) -> bool:
        return self.role in ("owner", "admin", "manager", "staff", "super_admin")
