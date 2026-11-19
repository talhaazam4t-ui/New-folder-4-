"""Schemas for the Teloxtech Services Assistant Chatbot."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ChatMessagePayload(BaseModel):
    role: str = Field(..., description="Role: 'user', 'assistant', or 'model'")
    content: str = Field(..., min_length=1, max_length=2000, description="Message content")


class AssistantChatRequest(BaseModel):
    messages: List[ChatMessagePayload] = Field(..., min_length=1)
    visitor_name: Optional[str] = None
    business_type: Optional[str] = None
    contact_info: Optional[str] = None
    api_key: Optional[str] = Field(
        default=None,
        description="Optional client-provided API Key (Gemini or DeepSeek)"
    )
    model: Optional[str] = Field(
        default="deepseek-chat",
        description="Target model (e.g. deepseek-chat, deepseek-reasoner, gemini-2.5-flash-lite)"
    )


class AssistantChatResponse(BaseModel):
    success: bool = True
    reply: str
    model_used: str
    action_url: Optional[str] = None
    action_label: Optional[str] = None
    service_slug: Optional[str] = None
    service_name: Optional[str] = None
    captured_lead: Optional[Dict[str, Any]] = None
