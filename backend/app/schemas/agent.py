"""Pydantic Schemas for Multi-Agent Orchestration, Registry, and Telemetry.
"""

from typing import Any, Dict, List, Literal, Optional
import uuid

from pydantic import BaseModel, Field


class AgentInfoResponse(BaseModel):
    name: str
    category: str
    description: str
    version: str = "1.0.0"
    allowed_tools: List[str]
    max_steps: int
    enabled_for_tenant: bool = True
    execution_limit: int = 1000
    budget_limit: float = 50.0


class TenantAgentConfigRequest(BaseModel):
    enabled: bool = True
    execution_limit: int = Field(default=1000, ge=1, le=100000)
    budget_limit: float = Field(default=50.0, ge=0.0, le=10000.0)
    configuration: Optional[Dict[str, Any]] = None


class AgentOrchestrateRequest(BaseModel):
    objective: str = Field(min_length=3, max_length=2000)
    agent_name: str = Field(default="master_orchestrator", max_length=100)
    action_type: Optional[str] = Field(default=None, max_length=100)
    requested_tool: Optional[str] = Field(default=None, max_length=100)
    context_data: Optional[Dict[str, Any]] = None


class AgentStageResult(BaseModel):
    agent_name: str
    role: str
    model: str
    output: str
    tokens_used: int
    estimated_cost: float


class AgentOrchestrateResponse(BaseModel):
    task_id: uuid.UUID
    tenant_id: uuid.UUID
    agent_name: str
    status: str
    objective: str
    requires_approval: bool = False
    approval_id: Optional[uuid.UUID] = None
    stages: List[AgentStageResult] = Field(default_factory=list)
    final_output: Optional[str] = None
    total_tokens: int = 0
    total_estimated_cost: float = 0.0


class OutreachAutopilotConfigUpdate(BaseModel):
    enabled: Optional[bool] = None
    niches: Optional[List[str]] = Field(default=None, max_length=20)
    cities: Optional[List[str]] = Field(default=None, max_length=40)
    channels: Optional[List[str]] = Field(default=None, max_length=5)
    require_human_approval: Optional[bool] = None
    daily_draft_limit: Optional[int] = Field(default=None, ge=1, le=15)
    service_offer: Optional[str] = Field(default=None, max_length=1200)
    sender_name: Optional[str] = Field(default=None, max_length=150)
    booking_url: Optional[str] = Field(default=None, max_length=500)
    run_hour_utc: Optional[int] = Field(default=None, ge=0, le=23)


class OutreachAutopilotRunRequest(BaseModel):
    niche: Optional[str] = Field(default=None, max_length=120)
    city: Optional[str] = Field(default=None, max_length=120)
    limit: Optional[int] = Field(default=None, ge=1, le=15)
    sync_pending_crm_drafts: bool = False


class OutreachLeadApproveRequest(BaseModel):
    channel: Literal["gmail", "whatsapp", "linkedin"]
    mode: Literal["send", "draft"] = "send"
    custom_subject: Optional[str] = Field(default=None, max_length=200)
    custom_body: Optional[str] = Field(default=None, max_length=4000)


class OutreachLeadRejectRequest(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=500)

