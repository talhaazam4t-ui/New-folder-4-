"""Teloxtech Services Assistant — API Route.

Provides a fast, public-facing conversational AI endpoint powered by DeepSeek AI
(`deepseek-chat`) for interactive lead qualification, managed service recommendations,
and Client Service Dashboard redirect guidance.
"""

from app.schemas.assistant import AssistantChatRequest, AssistantChatResponse
from app.services.assistant_service import assistant_service
from fastapi import APIRouter, status

router = APIRouter(prefix="/assistant", tags=["Services Assistant Chatbot"])


@router.post("/chat", response_model=AssistantChatResponse, status_code=status.HTTP_200_OK)
async def chat_with_services_assistant(request: AssistantChatRequest) -> AssistantChatResponse:
    """Conversational endpoint powered by DeepSeek AI for lead capture and service recommendations."""
    return await assistant_service.chat(request)
