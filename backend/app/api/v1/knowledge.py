"""1-Click RAG Knowledge Base API Endpoints (Website URL Crawl, PDF Upload & Semantic Vector Search)."""

import uuid
from typing import Optional

from app.core.tenant_context import TenantContext
from app.database.supabase import get_db
from app.dependencies import require_permission
from app.services.rag_service import rag_service
from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/knowledge", tags=["RAG Knowledge Base"])


class UrlIngestRequest(BaseModel):
    url: str = Field(min_length=4, max_length=1000)
    title: Optional[str] = Field(default=None, max_length=250)


class TextIngestRequest(BaseModel):
    title: str = Field(min_length=2, max_length=250)
    content: str = Field(min_length=10, max_length=150000)


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    top_k: int = Field(default=4, ge=1, le=10)


@router.get("/documents")
async def list_knowledge_documents(
    context: TenantContext = Depends(require_permission("tenant.read")),
    session: AsyncSession = Depends(get_db),
):
    """List indexed knowledge base documents for the active workspace."""
    docs = await rag_service.list_documents(session, context.tenant_id)
    return {"success": True, "data": docs}


@router.post("/ingest/url", status_code=status.HTTP_201_CREATED)
async def ingest_website_url(
    request: UrlIngestRequest,
    context: TenantContext = Depends(require_permission("integrations.manage")),
    session: AsyncSession = Depends(get_db),
):
    """Scrape a public website URL in 1 click, chunk it, and store pgvector embeddings."""
    doc = await rag_service.ingest_url(
        session=session,
        tenant_id=context.tenant_id,
        url=request.url,
        title=request.title,
        actor_id=context.user_id,
    )
    return {"success": True, "data": doc, "message": "Website indexed into RAG knowledge base"}


@router.post("/ingest/pdf", status_code=status.HTTP_201_CREATED)
async def ingest_pdf_document(
    file: UploadFile = File(...),
    title: Optional[str] = Form(default=None),
    context: TenantContext = Depends(require_permission("integrations.manage")),
    session: AsyncSession = Depends(get_db),
):
    """Extract text from an uploaded PDF (brochure/pricing/FAQ) and store vector embeddings."""
    pdf_bytes = await file.read()
    doc = await rag_service.ingest_pdf(
        session=session,
        tenant_id=context.tenant_id,
        filename=file.filename or "document.pdf",
        pdf_bytes=pdf_bytes,
        title=title,
        actor_id=context.user_id,
    )
    return {"success": True, "data": doc, "message": "PDF indexed into RAG knowledge base"}


@router.post("/ingest/text", status_code=status.HTTP_201_CREATED)
async def ingest_plain_text(
    request: TextIngestRequest,
    context: TenantContext = Depends(require_permission("integrations.manage")),
    session: AsyncSession = Depends(get_db),
):
    """Index custom text notes or SOPs into the tenant's RAG knowledge base."""
    doc = await rag_service.ingest_text(
        session=session,
        tenant_id=context.tenant_id,
        title=request.title,
        raw_text=request.content,
        source_type="text",
        actor_id=context.user_id,
    )
    return {"success": True, "data": doc, "message": "Knowledge article indexed cleanly"}


@router.post("/search")
async def search_knowledge_base(
    request: KnowledgeSearchRequest,
    context: TenantContext = Depends(require_permission("tenant.read")),
    session: AsyncSession = Depends(get_db),
):
    """Perform semantic vector retrieval across the active tenant's indexed documents."""
    matches = await rag_service.search_knowledge(
        session=session,
        tenant_id=context.tenant_id,
        query=request.query,
        top_k=request.top_k,
    )
    return {"success": True, "data": matches}


@router.delete("/documents/{document_id}")
async def delete_knowledge_document(
    document_id: uuid.UUID,
    context: TenantContext = Depends(require_permission("integrations.manage")),
    session: AsyncSession = Depends(get_db),
):
    """Delete an indexed knowledge document and all its vector chunks."""
    await rag_service.delete_document(session, context.tenant_id, document_id)
    return {"success": True, "message": "Knowledge document deleted"}
