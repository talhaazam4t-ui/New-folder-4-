"""Teloxtech Services Assistant — API Route.

Provides a fast, public-facing conversational AI endpoint powered by Google Gemini Flash-Lite
(`gemini-2.5-flash-lite`) and DeepSeek AI for interactive lead qualification, managed service recommendations,
and Client Service Dashboard redirect guidance.
"""

from app.config import settings
from app.core.rate_limit import limiter
from app.schemas.assistant import AssistantChatRequest, AssistantChatResponse
from app.services.assistant_service import assistant_service
from fastapi import APIRouter, Request, status

router = APIRouter(prefix="/assistant", tags=["Services Assistant Chatbot"])


@router.post("/chat", response_model=AssistantChatResponse, status_code=status.HTTP_200_OK)
@limiter.limit(f"{settings.rate_limit_agent_rpm}/minute")
async def chat_with_services_assistant(
    request: Request,
    payload: AssistantChatRequest,
) -> AssistantChatResponse:
    """Conversational endpoint powered by Gemini Flash-Lite and DeepSeek AI for lead capture and service recommendations."""
    return await assistant_service.chat(payload)
