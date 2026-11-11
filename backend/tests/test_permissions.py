from app.core.permissions import get_role_permissions, has_role_permission


def test_owner_permissions():
    perms = get_role_permissions("owner")
    assert "tenant.delete" in perms
    assert "tenant.update" in perms
    assert "business.records.delete" in perms
    assert "payments.refund" in perms
    assert "marketing.campaign.publish" in perms
    assert has_role_permission("owner", "tenant.delete") is True


def test_admin_permissions():
    perms = get_role_permissions("admin")
    assert "tenant.update" in perms
    assert "business.records.create" in perms
    # Admin cannot delete tenant workspace (only owner can)
    assert "tenant.delete" not in perms
    assert has_role_permission("admin", "tenant.delete") is False


def test_manager_permissions():
    assert has_role_permission("manager", "business.records.create") is True
    assert has_role_permission("manager", "marketing.campaign.create") is True
    # Manager cannot invite or manage employees
    assert has_role_permission("manager", "tenant.members.manage") is False
    assert has_role_permission("manager", "payments.refund") is False


def test_staff_permissions():
    assert has_role_permission("staff", "business.records.create") is True
    assert has_role_permission("staff", "business.records.read") is True
    # Staff cannot delete records or publish campaigns
    assert has_role_permission("staff", "business.records.delete") is False
    assert has_role_permission("staff", "marketing.campaign.publish") is False


def test_viewer_permissions():
    assert has_role_permission("viewer", "business.records.read") is True
    assert has_role_permission("viewer", "business.records.create") is False
    assert has_role_permission("viewer", "agents.execute") is False
