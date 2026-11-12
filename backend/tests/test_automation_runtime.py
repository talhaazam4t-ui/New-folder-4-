import pytest
from app.automation.budget_manager import budget_manager
from app.automation.runtime import automation_runtime
from app.main import app
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_automation_task_execution_retry_and_dlq():
    """Verify standard task execution, transient retry recovery, and permanent failure DLQ logging."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        reg = await client.post("/api/v1/auth/register", json={
            "email": "ops@automations.io",
            "password": "Password123!",
            "full_name": "Ops Lead",
        })
        token = reg.json()["access_token"]
        t_res = await client.post("/api/v1/tenants", json={
            "name": "Velocity Logistics",
            "slug": "velocity-logistics",
            "industry": "Logistics",
        }, headers={"Authorization": f"Bearer {token}"})
        tenant_id = t_res.json()["id"]
        budget_manager.admin_reset_circuit(tenant_id)
        headers = {"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_id}

        # 1. Execute normal simple task
        task_res = await client.post("/api/v1/tasks", json={
            "task_type": "whatsapp_reply",
            "input": {"prompt": "Confirm delivery schedule for Order #801"},
            "execute_immediately": True,
        }, headers=headers)
        assert task_res.status_code == 201
        task_data = task_res.json()
        assert task_data["status"] == "completed"
        assert task_data["attempts"] == 1
        assert "result" in task_data["output"]

        # 2. Execute task with simulated transient failure -> recovers on retry attempt 2
        retry_res = await client.post("/api/v1/tasks", json={
            "task_type": "simple_support",
            "input": {
                "prompt": "Check shipment status",
                "simulate_transient_failure": True,
            },
            "execute_immediately": True,
        }, headers=headers)
        assert retry_res.status_code == 201
        retry_data = retry_res.json()
        assert retry_data["status"] == "completed"
        assert retry_data["attempts"] == 2

        # 3. Execute task with permanent failure -> fails after 3 attempts & enters Dead-Letter Queue
        fail_res = await client.post("/api/v1/tasks", json={
            "task_type": "simple_support",
            "input": {"simulate_permanent_failure": True},
            "execute_immediately": True,
        }, headers=headers)
        assert fail_res.status_code == 201
        fail_data = fail_res.json()
        assert fail_data["status"] == "failed"
        assert fail_data["attempts"] == 3

        dlq_items = automation_runtime.dlq.list_entries(tenant_id=tenant_id)
        assert any(item["task_id"] == fail_data["id"] for item in dlq_items)


@pytest.mark.asyncio
async def test_human_approval_interception_approve_and_reject_workflows():
    """Verify sensitive actions are held in awaiting_approval until human approves or rejects."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        reg = await client.post("/api/v1/auth/register", json={
            "email": "director@growthagency.io",
            "password": "Password123!",
            "full_name": "Agency Director",
        })
        token = reg.json()["access_token"]
        t_res = await client.post("/api/v1/tenants", json={
            "name": "Apex Growth Agency",
            "slug": "apex-growth-agency",
            "industry": "Marketing",
        }, headers={"Authorization": f"Bearer {token}"})
        tenant_id = t_res.json()["id"]
        budget_manager.admin_reset_circuit(tenant_id)
        headers = {"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_id}

        # 1. Submit sensitive action (`publish_marketing_campaign`)
        sensitive_res = await client.post("/api/v1/tasks", json={
            "task_type": "publish_marketing_campaign",
            "input": {"campaign_name": "Q4 Holiday Launch", "budget_usd": 1500},
            "execute_immediately": True,
        }, headers=headers)
        assert sensitive_res.status_code == 201
        sensitive_task = sensitive_res.json()
        assert sensitive_task["status"] == "awaiting_approval"
        task_id = sensitive_task["id"]

        # 2. Attempting direct execution before approval keeps task in awaiting_approval
        direct_exec = await client.post(f"/api/v1/tasks/{task_id}/execute", headers=headers)
        assert direct_exec.status_code == 200
        assert direct_exec.json()["status"] == "awaiting_approval"

        # 3. Fetch pending approvals for tenant
        approvals_res = await client.get("/api/v1/approvals?status=pending", headers=headers)
        assert approvals_res.status_code == 200
        approvals = approvals_res.json()
        assert len(approvals) == 1
        approval_id = approvals[0]["id"]
        assert approvals[0]["task_id"] == task_id

        # 4. Owner approves the action -> task automatically executes and completes
        approve_res = await client.post(f"/api/v1/approvals/{approval_id}/approve", json={
            "reason": "Reviewed ad creative and budget cap; approved for launch.",
        }, headers=headers)
        assert approve_res.status_code == 200
        approve_payload = approve_res.json()["data"]
        assert approve_payload["approval"]["status"] == "approved"
        assert approve_payload["task"]["status"] == "completed"

        # 5. Submit another sensitive action (`send_bulk_whatsapp`) and reject it
        bulk_res = await client.post("/api/v1/tasks", json={
            "task_type": "send_bulk_whatsapp",
            "input": {"recipient_count": 500, "template": "promo_blast"},
            "execute_immediately": True,
        }, headers=headers)
        assert bulk_res.status_code == 201
        bulk_task_id = bulk_res.json()["id"]

        pending_list = (await client.get("/api/v1/approvals?status=pending", headers=headers)).json()
        reject_approval_id = next(a["id"] for a in pending_list if a["task_id"] == bulk_task_id)

        reject_res = await client.post(f"/api/v1/approvals/{reject_approval_id}/reject", json={
            "reason": "Recipient list not yet verified for opt-in compliance.",
        }, headers=headers)
        assert reject_res.status_code == 200
        assert reject_res.json()["status"] == "rejected"

        # Verify task transitioned to cancelled
        cancelled_task = (await client.get(f"/api/v1/tasks/{bulk_task_id}", headers=headers)).json()
        assert cancelled_task["status"] == "cancelled"


@pytest.mark.asyncio
async def test_scheduler_and_event_bus():
    """Verify APScheduler job registration and EventBus history tracking."""
    async def dummy_job():
        pass

    job_info = automation_runtime.scheduler.schedule_interval_job(
        job_id="test_rent_reminder_scan",
        func=dummy_job,
        seconds=3600,
    )
    assert job_info["job_id"] == "test_rent_reminder_scan"
    jobs = automation_runtime.scheduler.list_jobs()
    assert any(j["id"] == "test_rent_reminder_scan" for j in jobs)

    events = automation_runtime.event_bus.get_recent_events(limit=10)
    assert len(events) > 0
