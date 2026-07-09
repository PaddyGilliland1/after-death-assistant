"""Documents API: upload, list, metadata, download, versions, soft delete.

Access control (enforced server-side, never trusted from the client):
- A document with a non-empty access_roles list is only visible to the
  roles named in it.
- executor_private documents are never returned to the viewer role.
- Hidden documents 404 rather than 403, so their existence is not leaked.
Every write emits an audit event. Sensitive reads are audited too
(VALIDATION.md RQ-3): every download emits a "download" audit event, and
reading the metadata of an executor_private document emits "view_private".
"""

import re
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import ReadUser, Role, WriteUser
from app.db import get_session
from app.models import Document
from app.models.base import utcnow
from app.schemas.collab import ROLE_NAMES, DocumentOut
from app.services.seeding import get_active_estate, record_audit
from app.services.storage import StorageError, get_storage

router = APIRouter(prefix="/documents", tags=["documents"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

_FILENAME_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _parse_access_roles(raw: str) -> list[str]:
    roles = [item.strip().lower() for item in raw.split(",") if item.strip()]
    invalid = [role for role in roles if role not in ROLE_NAMES]
    if invalid:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown access roles: {', '.join(invalid)}. "
            f"Allowed: {', '.join(sorted(ROLE_NAMES))}.",
        )
    return roles


def _visible_to(document: Document, role: Role) -> bool:
    if document.archived_at is not None:
        return False
    if role == Role.VIEWER and document.executor_private:
        return False
    if document.access_roles and role.value not in document.access_roles:
        return False
    return True


async def _get_estate_id(session: AsyncSession) -> uuid.UUID:
    estate = await get_active_estate(session)
    if estate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No estate is configured yet. Seed one first.",
        )
    return estate.id


async def _get_document(session: AsyncSession, document_id: uuid.UUID) -> Document:
    document = await session.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    return document


def _download_filename(document: Document) -> str:
    stem = _FILENAME_SAFE_RE.sub("_", document.title).strip("._") or "document"
    suffix = Path(document.file_key or "").suffix
    return f"{stem}{suffix}"


@router.post("", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def upload_document(
    user: WriteUser,
    session: SessionDep,
    file: Annotated[UploadFile, File()],
    title: Annotated[str, Form(min_length=1)],
    doc_type: Annotated[str | None, Form(alias="type")] = None,
    access_roles: Annotated[str, Form()] = "",
    executor_private: Annotated[bool, Form()] = False,
) -> Document:
    """Store the uploaded file and create the document row (version 1)."""
    estate_id = await _get_estate_id(session)
    roles = _parse_access_roles(access_roles)
    data = await file.read()
    suffix = Path(file.filename or "").suffix
    file_key = get_storage().save(data, suffix=suffix)

    document = Document(
        estate_id=estate_id,
        title=title,
        type=doc_type,
        file_key=file_key,
        mime=file.content_type,
        version=1,
        access_roles=roles,
        executor_private=executor_private,
        created_by=user.email,
    )
    session.add(document)
    await session.flush()
    await record_audit(
        session,
        estate_id,
        user.email,
        "create",
        f"document:{document.id}",
        after={"title": title, "type": doc_type, "version": 1, "mime": file.content_type},
    )
    await session.commit()
    return document


@router.get("", response_model=list[DocumentOut])
async def list_documents(user: ReadUser, session: SessionDep) -> list[Document]:
    """List documents the caller's role is allowed to see, newest first."""
    estate_id = await _get_estate_id(session)
    result = await session.execute(
        select(Document)
        .where(Document.estate_id == estate_id, Document.archived_at.is_(None))
        .order_by(Document.created_at.desc())
    )
    return [doc for doc in result.scalars().all() if _visible_to(doc, user.role)]


@router.get("/{document_id}", response_model=DocumentOut)
async def get_document(
    document_id: uuid.UUID, user: ReadUser, session: SessionDep
) -> Document:
    """Document metadata, subject to the same visibility rules as the list.

    Reads of executor_private metadata are audited as "view_private"
    (VALIDATION.md RQ-3): these are the records the executors chose to
    shield, so access to them is part of the accountability trail.
    """
    document = await _get_document(session, document_id)
    if not _visible_to(document, user.role):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    if document.executor_private:
        await record_audit(
            session,
            document.estate_id,
            user.email,
            "view_private",
            f"document:{document.id}",
            after={"title": document.title, "version": document.version},
        )
        await session.commit()
    return document


@router.get("/{document_id}/download")
async def download_document(
    document_id: uuid.UUID, user: ReadUser, session: SessionDep
) -> StreamingResponse:
    """Stream the stored file bytes.

    Every successful download emits a "download" audit event naming the
    actor (VALIDATION.md RQ-3: read access to sensitive records is part of
    "who created, changed, viewed or approved what").
    """
    document = await _get_document(session, document_id)
    if not _visible_to(document, user.role):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    if not document.file_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document has no stored file."
        )
    storage = get_storage()
    try:
        stream = storage.stream(document.file_key)
    except StorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Stored file is missing."
        ) from exc
    await record_audit(
        session,
        document.estate_id,
        user.email,
        "download",
        f"document:{document.id}",
        after={
            "title": document.title,
            "version": document.version,
            "file_key": document.file_key,
        },
    )
    await session.commit()
    return StreamingResponse(
        stream,
        media_type=document.mime or "application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{_download_filename(document)}"'
        },
    )


@router.post("/{document_id}/versions", response_model=DocumentOut)
async def upload_new_version(
    document_id: uuid.UUID,
    user: WriteUser,
    session: SessionDep,
    file: Annotated[UploadFile, File()],
) -> Document:
    """Attach a new file version; the previous file key is kept in links."""
    document = await _get_document(session, document_id)
    if document.archived_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    before = {"version": document.version, "file_key": document.file_key}
    data = await file.read()
    suffix = Path(file.filename or "").suffix
    new_key = get_storage().save(data, suffix=suffix)

    links = list(document.links or [])
    if document.file_key:
        links.append(
            {
                "kind": "previous_version",
                "version": document.version,
                "file_key": document.file_key,
            }
        )
    document.links = links
    document.file_key = new_key
    document.mime = file.content_type
    document.version = document.version + 1
    document.updated_at = utcnow()
    session.add(document)
    await session.flush()
    await record_audit(
        session,
        document.estate_id,
        user.email,
        "update",
        f"document:{document.id}",
        before=before,
        after={"version": document.version, "file_key": new_key},
    )
    await session.commit()
    return document


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_document(
    document_id: uuid.UUID,
    user: WriteUser,
    session: SessionDep,
    reason: Annotated[str | None, Body(embed=True)] = None,
) -> None:
    """Soft delete: archive the row. The stored file is retained."""
    document = await _get_document(session, document_id)
    if document.archived_at is not None:
        return
    document.archived_at = utcnow()
    document.archive_reason = reason
    session.add(document)
    await session.flush()
    await record_audit(
        session,
        document.estate_id,
        user.email,
        "archive",
        f"document:{document.id}",
        before={"title": document.title, "version": document.version},
        after={"archive_reason": reason},
    )
    await session.commit()
