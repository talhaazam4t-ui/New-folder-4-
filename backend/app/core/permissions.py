"""Role-Based Access Control (RBAC) and Permission Matrix.

Defines all platform permissions and maps roles (owner, admin, manager, staff, viewer)
to permitted operations.
"""

from typing import Set

# Platform Permissions Definition
PERMISSIONS = {
    # Tenant
    "tenant.read": "View tenant settings and company profile",
    "tenant.update": "Modify tenant settings and details",
    "tenant.delete": "Delete or terminate tenant account and purge data",
    "tenant.members.manage": "Invite and manage tenant employees",

    # Business
    "business.records.read": "View income, expense, and rent records",
    "business.records.create": "Create income, expense, or rent records",
    "business.records.update": "Edit allowed business records",
    "business.records.delete": "Delete business records (Requires Approval)",
    "business.metrics.read": "View business analytics and metrics",

    # Marketing
    "marketing.research": "Run competitor research and audience discovery",
    "marketing.content.generate": "Generate marketing copy and assets",
    "marketing.campaign.create": "Draft new marketing campaigns",
    "marketing.campaign.publish": "Launch live campaigns (Requires Approval)",
    "leads.read": "View leads and contact info",
    "leads.create": "Add new leads",
    "leads.update": "Update lead status and qualification score",

    # Billing & Payments
    "payments.read": "View payment history and invoices",
    "payments.create": "Initiate payment",
    "payments.refund": "Issue payment refund (Requires Approval)",
    "subscriptions.read": "View subscription status and plans",
    "subscriptions.update": "Upgrade, downgrade, or cancel subscription",

    # Notifications & Integrations
    "notifications.send": "Send customer alerts and notifications",
    "integrations.read": "View connected integrations",
    "integrations.manage": "Connect or disconnect WhatsApp, email, or third-party apps",

    # Agents & Automation
    "agents.execute": "Trigger agent execution on tasks",
    "agents.configure": "Configure agent budget and parameters",
    "approvals.review": "Review and approve/reject pending actions",

    # System Admin
    "system.admin": "Platform owner administrative privilege",
}

# Role to Permissions Mapping
ROLE_PERMISSIONS_MAP = {
    "owner": {
        "tenant.read", "tenant.update", "tenant.delete", "tenant.members.manage",
        "business.records.read", "business.records.create", "business.records.update", "business.records.delete",
        "business.metrics.read",
        "marketing.research", "marketing.content.generate", "marketing.campaign.create", "marketing.campaign.publish",
        "leads.read", "leads.create", "leads.update",
        "payments.read", "payments.create", "payments.refund",
        "subscriptions.read", "subscriptions.update",
        "notifications.send", "integrations.read", "integrations.manage",
        "agents.execute", "agents.configure", "approvals.review",
    },
    "admin": {
        "tenant.read", "tenant.update", "tenant.members.manage",
        "business.records.read", "business.records.create", "business.records.update",
        "business.metrics.read",
        "marketing.research", "marketing.content.generate", "marketing.campaign.create",
        "leads.read", "leads.create", "leads.update",
        "payments.read", "subscriptions.read",
        "notifications.send", "integrations.read", "integrations.manage",
        "agents.execute", "agents.configure", "approvals.review",
    },
    "manager": {
        "tenant.read",
        "business.records.read", "business.records.create", "business.records.update",
        "business.metrics.read",
        "marketing.research", "marketing.content.generate", "marketing.campaign.create",
        "leads.read", "leads.create", "leads.update",
        "notifications.send", "integrations.read",
        "agents.execute",
    },
    "staff": {
        "tenant.read",
        "business.records.read", "business.records.create",
        "business.metrics.read",
        "leads.read", "leads.create",
        "agents.execute",
    },
    "viewer": {
        "tenant.read",
        "business.records.read",
        "business.metrics.read",
        "leads.read",
        "payments.read",
        "subscriptions.read",
    },
}


def get_role_permissions(role: str) -> Set[str]:
    """Retrieve the set of allowed permissions for a given role."""
    return ROLE_PERMISSIONS_MAP.get(role, set())


def has_role_permission(role: str, permission: str) -> bool:
    """Check if a role includes a specific permission."""
    return permission in get_role_permissions(role)
