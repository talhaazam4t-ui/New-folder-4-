"""In-House 1-Click RAG Knowledge Base Service (pgvector + Gemini Embeddings + Local Fallback).

Supports:
1. SSRF-safe website URL scraping via `httpx` + `BeautifulSoup`.
2. Direct PDF text extraction via `pypdf`.
3. Overlapping semantic text chunking and 768-dim embeddings (Gemini `text-embedding-004` with
   zero-cost deterministic L2-normalized trigram/token hashing fallback).
4. Native PostgreSQL `pgvector` HNSW cosine similarity search (with SQLite-compatible fallback).
"""

import hashlib
import io
import math
import re
import uuid
from typing import Any, Dict, List, Optional, Tuple

import httpx
from app.config import settings
from app.core.exceptions import ResourceNotFoundError, TaloxException
from app.core.logging import logger
from app.database.models.automation import AuditLog
from app.database.models.knowledge import KnowledgeChunk, KnowledgeDocument
from app.services.outreach_autopilot_service import _is_safe_public_url
from bs4 import BeautifulSoup
from pypdf import PdfReader
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

EMBEDDING_DIM = 768
MAX_PDF_BYTES = 10 * 1024 * 1024  # 10 MB


def _clean_whitespace(raw: str) -> str:
    return re.sub(r"\s+", " ", raw or "").strip()


def _normalize_vector(vec: List[float], target_dim: int = EMBEDDING_DIM) -> List[float]:
    trimmed = [float(x) for x in vec[:target_dim]]
    if len(trimmed) < target_dim:
        trimmed.extend([0.0] * (target_dim - len(trimmed)))
    norm = math.sqrt(sum(v * v for v in trimmed))
    if norm <= 1e-12:
        return trimmed
    return [round(v / norm, 6) for v in trimmed]


def _local_semantic_embedding(content: str, dim: int = EMBEDDING_DIM) -> List[float]:
    """Deterministic L2-normalized bag-of-tokens + char-trigram feature-hashing vector."""
    vec = [0.0] * dim
    cleaned = re.sub(r"[^a-z0-9\s]", " ", (content or "").lower())
    words = [w for w in cleaned.split() if len(w) >= 2]
    for word in words:
        h = int.from_bytes(hashlib.blake2b(f"w:{word}".encode("utf-8"), digest_size=4).digest(), "little")
        sign = 1.0 if (h & 1) == 0 else -1.0
        vec[(h >> 1) % dim] += sign * 2.0
        if len(word) >= 3:
            for i in range(len(word) - 2):
                tri = word[i : i + 3]
                th = int.from_bytes(hashlib.blake2b(f"t:{tri}".encode("utf-8"), digest_size=4).digest(), "little")
                tsign = 1.0 if (th & 1) == 0 else -1.0
                vec[(th >> 1) % dim] += tsign * 0.5
    return _normalize_vector(vec, dim)


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na <= 1e-12 or nb <= 1e-12:
        return 0.0
    return dot / (na * nb)


class RagKnowledgeService:
    """Manages 1-click knowledge ingestion, vector indexing, and tenant-isolated RAG search."""

    def chunk_text(self, raw_text: str, chunk_size: int = 750, overlap: int = 120) -> List[str]:
        normalized = _clean_whitespace(raw_text)
        if not normalized:
            return []
        if len(normalized) <= chunk_size:
            return [normalized]

        chunks: List[str] = []
        start = 0
        text_len = len(normalized)
        step = max(100, chunk_size - overlap)
        while start < text_len:
            end = min(text_len, start + chunk_size)
            if end < text_len:
                last_space = normalized.rfind(" ", start + int(chunk_size * 0.6), end)
                if last_space > start:
                    end = last_space
            piece = normalized[start:end].strip()
            if piece:
                chunks.append(piece)
            if end >= text_len:
                break
            start = max(start + step, end - overlap)
        return chunks

    async def extract_text_from_url(self, url: str) -> Tuple[str, str]:
        """Safely fetch a public URL and extract clean title + readable page content."""
        safe_url = _is_safe_public_url(url)
        if not safe_url:
            raise TaloxException(
                message="Invalid or restricted URL provided. Use a valid public http/https website URL.",
                code="INVALID_KNOWLEDGE_URL",
                status_code=400,
            )

        headers = {
            "User-Agent": "TaloxTech-KnowledgeCrawler/3.0 (+https://teloxtech.stream)",
            "Accept": "text/html,application/xhtml+xml,text/plain",
        }
        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                resp = await client.get(safe_url, headers=headers)
                resp.raise_for_status()
        except Exception as exc:
            raise TaloxException(
                message=f"Could not fetch website content: {str(exc)[:180]}",
                code="URL_FETCH_FAILED",
                status_code=502,
            )

        html = (resp.text or "")[:600_000]
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript", "svg", "iframe"]):
            tag.decompose()

        title = _clean_whitespace(soup.title.string) if soup.title and soup.title.string else safe_url
        blocks: List[str] = []
        for el in soup.find_all(["h1", "h2", "h3", "h4", "p", "li", "td", "th"]):
            txt = _clean_whitespace(el.get_text(" ", strip=True))
            if txt and len(txt) >= 12:
                blocks.append(txt)

        if not blocks:
            body_text = _clean_whitespace(soup.get_text(" ", strip=True))
        else:
            seen = set()
            deduped: List[str] = []
            for b in blocks:
                if b not in seen:
                    seen.add(b)
                    deduped.append(b)
            body_text = "\n".join(deduped)

        if len(body_text) < 20:
            raise TaloxException(
                message="No readable text content found on the target webpage.",
                code="EMPTY_URL_CONTENT",
                status_code=400,
            )
        return title[:240], body_text[:120_000]

    def extract_text_from_pdf(self, pdf_bytes: bytes) -> str:
        """Extract text from uploaded PDF bytes using pypdf."""
        if not pdf_bytes:
            raise TaloxException(message="Uploaded PDF file is empty.", code="EMPTY_PDF", status_code=400)
        if len(pdf_bytes) > MAX_PDF_BYTES:
            raise TaloxException(
                message="PDF exceeds 10 MB limit.",
                code="PDF_TOO_LARGE",
                status_code=400,
            )
        try:
            reader = PdfReader(io.BytesIO(pdf_bytes))
            pages_text = []
            for page in reader.pages[:60]:
                extracted = page.extract_text() or ""
                if extracted.strip():
                    pages_text.append(extracted.strip())
            combined = "\n".join(pages_text).strip()
        except Exception as exc:
            raise TaloxException(
                message=f"Could not parse PDF file: {str(exc)[:160]}",
                code="INVALID_PDF",
                status_code=400,
            )

        if len(combined) < 10:
            raise TaloxException(
                message="No extractable text found in PDF (scanned image-only PDFs are handled via OCR in Phase 4).",
                code="EMPTY_PDF_TEXT",
                status_code=400,
            )
        return combined[:150_000]

    async def generate_embedding(self, text_value: str) -> List[float]:
        """Generate a 768-dim embedding via Gemini API when configured, or local normalized vector fallback."""
        gem_key = (settings.gemini_api_key or "").strip()
        if gem_key and settings.app_env != "test":
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.post(
                        "https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:embedContent",
                        params={"key": gem_key},
                        json={
                            "model": "models/text-embedding-004",
                            "content": {"parts": [{"text": (text_value or "")[:6000]}]},
                        },
                    )
                    if resp.status_code == 200:
                        vals = ((resp.json().get("embedding") or {}).get("values")) or []
                        if vals:
                            return _normalize_vector([float(v) for v in vals], EMBEDDING_DIM)
            except Exception as exc:
                logger.debug("Gemini embedding fallback to local vectorizer", error=str(exc))
        return _local_semantic_embedding(text_value, EMBEDDING_DIM)

    def _serialize_document(self, doc: KnowledgeDocument) -> Dict[str, Any]:
        return {
            "id": str(doc.id),
            "tenant_id": str(doc.tenant_id),
            "title": doc.title,
            "source_type": doc.source_type,
            "source_url": doc.source_url,
            "status": doc.status,
            "chunk_count": doc.chunk_count,
            "char_count": doc.char_count,
            "metadata": doc.metadata_ or {},
            "created_at": doc.created_at.isoformat() if doc.created_at else None,
        }

    async def ingest_text(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        title: str,
        raw_text: str,
        source_type: str = "text",
        source_url: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        actor_id: Optional[uuid.UUID] = None,
    ) -> Dict[str, Any]:
        chunks = self.chunk_text(raw_text)
        if not chunks:
            raise TaloxException(
                message="Knowledge text cannot be empty.",
                code="EMPTY_KNOWLEDGE_TEXT",
                status_code=400,
            )

        doc = KnowledgeDocument(
            tenant_id=tenant_id,
            title=title.strip()[:250] or "Business Knowledge",
            source_type=source_type if source_type in ("url", "pdf", "text") else "text",
            source_url=source_url,
            status="indexed",
            chunk_count=len(chunks),
            char_count=len(raw_text),
            metadata_=dict(metadata or {}),
        )
        session.add(doc)
        await session.flush()

        chunk_rows: List[Tuple[KnowledgeChunk, List[float]]] = []
        for idx, chunk_str in enumerate(chunks):
            emb = await self.generate_embedding(chunk_str)
            kc = KnowledgeChunk(
                tenant_id=tenant_id,
                document_id=doc.id,
                chunk_index=idx,
                content=chunk_str,
                embedding_json=emb,
                token_estimate=max(1, len(chunk_str.split())),
                metadata_={"source_type": doc.source_type, "title": doc.title},
            )
            session.add(kc)
            chunk_rows.append((kc, emb))

        await session.flush()

        bind = session.get_bind()
        if bind is not None and bind.dialect.name == "postgresql":
            for kc, emb in chunk_rows:
                vec_literal = "[" + ",".join(f"{v:.6f}" for v in emb) + "]"
                await session.execute(
                    text(
                        "UPDATE public.knowledge_chunks SET embedding = CAST(:vec AS extensions.vector) WHERE id = :cid"
                    ),
                    {"vec": vec_literal, "cid": str(kc.id)},
                )

        session.add(
            AuditLog(
                tenant_id=tenant_id,
                actor_id=actor_id,
                actor_type="user" if actor_id else "system",
                action="knowledge.document.indexed",
                resource_type="knowledge_document",
                resource_id=doc.id,
                metadata_={
                    "title": doc.title,
                    "source_type": doc.source_type,
                    "chunk_count": len(chunks),
                },
            )
        )
        await session.commit()
        await session.refresh(doc)
        return self._serialize_document(doc)

    async def ingest_url(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        url: str,
        title: Optional[str] = None,
        actor_id: Optional[uuid.UUID] = None,
    ) -> Dict[str, Any]:
        page_title, extracted_text = await self.extract_text_from_url(url)
        return await self.ingest_text(
            session=session,
            tenant_id=tenant_id,
            title=(title or page_title).strip(),
            raw_text=extracted_text,
            source_type="url",
            source_url=url.strip(),
            metadata={"crawled_url": url.strip()},
            actor_id=actor_id,
        )

    async def ingest_pdf(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        filename: str,
        pdf_bytes: bytes,
        title: Optional[str] = None,
        actor_id: Optional[uuid.UUID] = None,
    ) -> Dict[str, Any]:
        extracted_text = self.extract_text_from_pdf(pdf_bytes)
        clean_title = (title or filename or "Uploaded Document").strip()
        return await self.ingest_text(
            session=session,
            tenant_id=tenant_id,
            title=clean_title,
            raw_text=extracted_text,
            source_type="pdf",
            metadata={"filename": filename, "byte_size": len(pdf_bytes)},
            actor_id=actor_id,
        )

    async def list_documents(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> List[Dict[str, Any]]:
        res = await session.execute(
            select(KnowledgeDocument)
            .where(KnowledgeDocument.tenant_id == tenant_id)
            .order_by(KnowledgeDocument.created_at.desc())
        )
        return [self._serialize_document(d) for d in res.scalars().all()]

    async def delete_document(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        document_id: uuid.UUID,
    ) -> bool:
        res = await session.execute(
            select(KnowledgeDocument).where(
                KnowledgeDocument.id == document_id,
                KnowledgeDocument.tenant_id == tenant_id,
            )
        )
        doc = res.scalar_one_or_none()
        if not doc:
            raise ResourceNotFoundError("KnowledgeDocument", str(document_id))

        await session.execute(
            delete(KnowledgeChunk).where(
                KnowledgeChunk.document_id == document_id,
                KnowledgeChunk.tenant_id == tenant_id,
            )
        )
        await session.delete(doc)
        await session.commit()
        return True

    async def search_knowledge(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        query: str,
        top_k: int = 4,
    ) -> List[Dict[str, Any]]:
        """Retrieve top relevant knowledge chunks strictly isolated to `tenant_id`."""
        clean_query = _clean_whitespace(query)
        if not clean_query:
            return []

        q_emb = await self.generate_embedding(clean_query)
        k = min(max(int(top_k), 1), 10)

        bind = session.get_bind()
        if bind is not None and bind.dialect.name == "postgresql":
            try:
                vec_literal = "[" + ",".join(f"{v:.6f}" for v in q_emb) + "]"
                pg_res = await session.execute(
                    text(
                        """
                        SELECT kc.id::text AS chunk_id,
                               kc.document_id::text AS document_id,
                               kd.title AS document_title,
                               kd.source_type AS source_type,
                               kc.content AS content,
                               (1.0 - (kc.embedding <=> CAST(:qvec AS extensions.vector))) AS score
                        FROM public.knowledge_chunks kc
                        JOIN public.knowledge_documents kd ON kd.id = kc.document_id
                        WHERE kc.tenant_id = :tid AND kc.embedding IS NOT NULL
                        ORDER BY kc.embedding <=> CAST(:qvec AS extensions.vector) ASC
                        LIMIT :lim
                        """
                    ),
                    {"qvec": vec_literal, "tid": str(tenant_id), "lim": k},
                )
                pg_rows = pg_res.mappings().all()
                if pg_rows:
                    return [
                        {
                            "chunk_id": str(r["chunk_id"]),
                            "document_id": str(r["document_id"]),
                            "document_title": str(r["document_title"]),
                            "source_type": str(r["source_type"]),
                            "content": str(r["content"]),
                            "score": round(float(r["score"] or 0.0), 4),
                        }
                        for r in pg_rows
                    ]
            except Exception as exc:
                logger.warning("pgvector search fallback to JSON vector scoring", error=str(exc))

        stmt = (
            select(KnowledgeChunk, KnowledgeDocument.title, KnowledgeDocument.source_type)
            .join(KnowledgeDocument, KnowledgeChunk.document_id == KnowledgeDocument.id)
            .where(KnowledgeChunk.tenant_id == tenant_id)
        )
        res = await session.execute(stmt)
        rows = res.all()

        query_terms = {w for w in re.sub(r"[^a-z0-9\s]", " ", clean_query.lower()).split() if len(w) >= 3}
        scored: List[Tuple[float, Dict[str, Any]]] = []
        for kc, doc_title, src_type in rows:
            vec = kc.embedding_json if isinstance(kc.embedding_json, list) else []
            cos = _cosine_similarity(q_emb, vec)
            lower_content = (kc.content or "").lower()
            keyword_hits = sum(1 for t in query_terms if t in lower_content)
            boost = min(0.25, keyword_hits * 0.06)
            total_score = round(cos + boost, 4)
            scored.append(
                (
                    total_score,
                    {
                        "chunk_id": str(kc.id),
                        "document_id": str(kc.document_id),
                        "document_title": doc_title,
                        "source_type": src_type,
                        "content": kc.content,
                        "score": total_score,
                    },
                )
            )

        scored.sort(key=lambda item: -item[0])
        return [item[1] for item in scored[:k]]


rag_service = RagKnowledgeService()
