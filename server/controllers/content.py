"""HTTP routes for the content domain."""
import mimetypes
import xml.etree.ElementTree as ElementTree
import zlib
import zipfile
from io import BytesIO
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session, defer
from server.config import MAX_UPLOAD_BYTES
from server.controllers.common import record_audit, require_permission
from server.database import get_db
from server.models import AdminNotification, KnowledgeArticle, KnowledgeDomain, NOCProcess, ProcessDocument, User, UserRole, utc_now
from server.schemas import KnowledgeInput, KnowledgeRead, ProcessDocumentRead, ProcessInput, ProcessRead
from server.services.permissions import Permission
from server.services.process_service import ProcessService
from server.services.security import get_current_user, require_roles

router = APIRouter()

PROCESS_DOCUMENT_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".odt", ".rtf", ".xls", ".xlsx",
    ".ppt", ".pptx", ".txt", ".csv",
}

PROCESS_DOCUMENT_ZIP_REQUIREMENTS = {
    ".docx": ("[Content_Types].xml", "word/document.xml"),
    ".odt": ("mimetype", "content.xml"),
    ".pptx": ("[Content_Types].xml", "ppt/presentation.xml"),
    ".xlsx": ("[Content_Types].xml", "xl/workbook.xml"),
}
MAX_DOCUMENT_ARCHIVE_ENTRIES = 500
MAX_DOCUMENT_ARCHIVE_EXPANDED_BYTES = 64 * 1024 * 1024
MAX_DOCUMENT_ARCHIVE_ENTRY_BYTES = 32 * 1024 * 1024


def validate_process_document(suffix: str, content: bytes) -> None:
    if suffix == ".pdf":
        if not content.startswith(b"%PDF-") or b"%%EOF" not in content[-2048:]:
            raise ValueError("The uploaded file is not a valid PDF document")
        return
    if suffix in PROCESS_DOCUMENT_ZIP_REQUIREMENTS:
        try:
            with zipfile.ZipFile(BytesIO(content)) as archive:
                entries = archive.infolist()
                if len(entries) > MAX_DOCUMENT_ARCHIVE_ENTRIES:
                    raise ValueError("The Office document contains too many archive entries")
                expanded_size = sum(entry.file_size for entry in entries)
                if expanded_size > MAX_DOCUMENT_ARCHIVE_EXPANDED_BYTES or any(
                    entry.file_size > MAX_DOCUMENT_ARCHIVE_ENTRY_BYTES for entry in entries
                ):
                    raise ValueError("The Office document expands beyond the allowed size")
                names = set(archive.namelist())
                required = PROCESS_DOCUMENT_ZIP_REQUIREMENTS[suffix]
                if not set(required).issubset(names):
                    raise ValueError("The uploaded file does not match its Office document extension")
                for name in required:
                    package_content = archive.read(name)
                    if name.endswith(".xml"):
                        if b"<!DOCTYPE" in package_content.upper() or b"<!ENTITY" in package_content.upper():
                            raise ValueError("The Office document contains forbidden XML declarations")
                        ElementTree.fromstring(package_content)
                if suffix == ".odt":
                    mimetype = archive.read("mimetype").decode("ascii")
                    if mimetype != "application/vnd.oasis.opendocument.text":
                        raise ValueError("The uploaded file does not match its ODT extension")
        except (
            ElementTree.ParseError,
            zipfile.BadZipFile,
            KeyError,
            RuntimeError,
            UnicodeDecodeError,
            zlib.error,
        ) as exc:
            raise ValueError("The uploaded file is not a valid Office document") from exc
        return
    if suffix in {".doc", ".ppt", ".xls"}:
        if not content.startswith(bytes.fromhex("D0CF11E0A1B11AE1")):
            raise ValueError("The uploaded file is not a valid legacy Office document")
        return
    if suffix == ".rtf":
        if not content.startswith(b"{\\rtf") or not content.rstrip().endswith(b"}"):
            raise ValueError("The uploaded file is not a valid RTF document")
        return
    if suffix in {".txt", ".csv"}:
        try:
            content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError("Text and CSV documents must be UTF-8 encoded") from exc
        if b"\x00" in content:
            raise ValueError("Text and CSV documents cannot contain binary data")


@router.get("/api/v1/process-documents", response_model=list[ProcessDocumentRead])
def list_process_documents(
    db: Session = Depends(get_db),
    _actor: User = Depends(get_current_user),
):
    return db.scalars(
        select(ProcessDocument).options(defer(ProcessDocument.content)).order_by(ProcessDocument.created_at.desc())
    ).all()


@router.post("/api/v1/process-documents", status_code=201, response_model=ProcessDocumentRead)
def upload_process_document(
    request: Request,
    title: str = Form(default="", max_length=200),
    description: str = Form(default="", max_length=4000),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.admin)),
):
    original_name = Path(file.filename or "").name
    if not original_name or len(original_name) > 255:
        raise HTTPException(status_code=422, detail="Document filename must be 1-255 characters")
    suffix = Path(original_name).suffix.casefold()
    if suffix not in PROCESS_DOCUMENT_EXTENSIONS:
        raise HTTPException(status_code=415, detail="Upload a PDF, Office document, text, or CSV file")
    content = file.file.read(MAX_UPLOAD_BYTES + 1)
    if not content:
        raise HTTPException(status_code=422, detail="The uploaded document is empty")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Document exceeds the 10 MB upload limit")
    try:
        validate_process_document(suffix, content)
    except ValueError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc

    document_title = title.strip() or Path(original_name).stem.strip() or "NOC reference document"
    content_type = mimetypes.guess_type(original_name)[0] or "application/octet-stream"
    document = ProcessDocument(
        title=document_title[:200],
        description=description.strip() or None,
        file_name=original_name,
        content_type=content_type,
        content=content,
        uploaded_by_id=actor.id,
    )
    db.add(document)
    db.flush()
    record_audit(db, actor, "process_document.uploaded", "process_document", document.id)
    db.commit()
    db.refresh(document)
    if "text/html" in request.headers.get("accept", ""):
        return RedirectResponse("/shift-portal.html#process", status_code=303)
    return document


@router.get("/api/v1/process-documents/{document_id}/view")
def view_process_document(
    document_id: int,
    db: Session = Depends(get_db),
    _actor: User = Depends(get_current_user),
):
    document = db.get(ProcessDocument, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    media_type = document.content_type
    if media_type not in {"application/pdf", "text/plain", "text/csv"}:
        media_type = "application/octet-stream"
    return StreamingResponse(
        BytesIO(document.content),
        media_type=media_type,
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{quote(document.file_name)}",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/api/v1/process-documents/{document_id}/download")
def download_process_document(
    document_id: int,
    db: Session = Depends(get_db),
    _actor: User = Depends(get_current_user),
):
    document = db.get(ProcessDocument, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return StreamingResponse(
        BytesIO(document.content),
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(document.file_name)}",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.delete("/api/v1/process-documents/{document_id}")
def delete_process_document(
    document_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.admin)),
):
    document = db.get(ProcessDocument, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    record_audit(db, actor, "process_document.deleted", "process_document", document.id)
    db.delete(document)
    db.commit()
    return {"status": "success"}

@router.get("/api/v1/process", response_model=list[ProcessRead])
def list_processes(
    category: str | None = None,
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    return ProcessService(db).list_active(category=category, limit=limit, offset=offset)


@router.post("/api/v1/process", status_code=201, response_model=ProcessRead)
def create_process(
    payload: ProcessInput,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(Permission.edit_process_articles)),
):
    process = NOCProcess(
        **payload.model_dump(exclude={"expected_updated_at"}),
        created_by_id=actor.id,
    )
    process_service = ProcessService(db)
    process_service.repository.add(process)
    record_audit(db, actor, "process.created", "process", process.id)
    process_service.repository.save()
    process_service.repository.refresh(process)
    return process


@router.put("/api/v1/process/{process_id}", response_model=ProcessRead)
def update_process(
    process_id: int,
    payload: ProcessInput,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(Permission.edit_process_articles)),
):
    process = db.get(NOCProcess, process_id)
    if process is None:
        raise HTTPException(status_code=404, detail="Process record not found")
    if payload.expected_updated_at is None:
        raise HTTPException(
            status_code=428,
            detail="Reload this process before editing so the latest version is included.",
        )
    locked_at = utc_now()
    claim = db.execute(
        update(NOCProcess)
        .where(
            NOCProcess.id == process.id,
            NOCProcess.updated_at == payload.expected_updated_at,
        )
        .values(updated_at=locked_at)
        .execution_options(synchronize_session=False)
    )
    if claim.rowcount != 1:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="This process changed after you opened it. Reload it before saving again.",
        )
    process.updated_at = locked_at
    for key, value in payload.model_dump(exclude={"expected_updated_at"}).items():
        setattr(process, key, value)
    record_audit(db, actor, "process.updated", "process", process.id)
    db.commit()
    db.refresh(process)
    return process


@router.get("/api/v1/knowledge-hub", response_model=list[KnowledgeRead])
def list_knowledge(
    domain: str | None = None,
    q: str | None = None,
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    query = select(KnowledgeArticle).where(
        KnowledgeArticle.is_active.is_(True),
        KnowledgeArticle.approval_status == "approved",
    )
    if domain:
        try:
            query = query.where(KnowledgeArticle.domain == KnowledgeDomain(domain))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Unknown knowledge domain") from exc
    if q:
        term = f"%{q}%"
        query = query.where(or_(
            KnowledgeArticle.issue_title.ilike(term),
            KnowledgeArticle.symptoms.ilike(term),
            KnowledgeArticle.root_cause.ilike(term),
            KnowledgeArticle.troubleshooting_steps.ilike(term),
            KnowledgeArticle.resolution.ilike(term),
        ))
    query = query.offset(offset).limit(limit)
    return db.scalars(query.order_by(KnowledgeArticle.domain, KnowledgeArticle.issue_title)).all()


@router.get("/api/v1/knowledge-hub/recent")
def recent_knowledge(db: Session = Depends(get_db)):
    results = {}
    domains = [KnowledgeDomain.power, KnowledgeDomain.ran, KnowledgeDomain.tx, KnowledgeDomain.core]
    for domain in domains:
        row = db.scalar(
            select(KnowledgeArticle)
            .where(
                KnowledgeArticle.domain == domain,
                KnowledgeArticle.is_active.is_(True),
                KnowledgeArticle.approval_status == "approved",
            )
            .order_by(KnowledgeArticle.created_at.desc())
            .limit(1)
        )
        results[domain.value] = KnowledgeRead.model_validate(row).model_dump(mode="json") if row else None
    return results


@router.get("/api/v1/knowledge-hub/pending")
def pending_knowledge(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin)),
):
    rows = db.execute(
        select(KnowledgeArticle, User.full_name, User.username)
        .join(User, User.id == KnowledgeArticle.created_by_id)
        .where(KnowledgeArticle.approval_status == "pending")
        .order_by(KnowledgeArticle.created_at.asc())
    ).all()
    return [
        {
            **KnowledgeRead.model_validate(article).model_dump(mode="json"),
            "author_name": author_name,
            "author_username": author_username,
        }
        for article, author_name, author_username in rows
    ]


@router.get("/api/v1/notifications")
def list_notifications(
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    rows = db.execute(
        select(AdminNotification, KnowledgeArticle.issue_title, KnowledgeArticle.domain)
        .join(KnowledgeArticle, KnowledgeArticle.id == AdminNotification.article_id)
        .where(AdminNotification.recipient_id == actor.id)
        .order_by(AdminNotification.created_at.desc())
        .limit(50)
    ).all()
    return [
        {
            "id": notification.id,
            "article_id": notification.article_id,
            "article_title": title,
            "domain": domain.value,
            "message": notification.message,
            "is_read": notification.is_read,
            "created_at": notification.created_at,
        }
        for notification, title, domain in rows
    ]


@router.patch("/api/v1/notifications/{notification_id}/read")
def mark_notification_read(
    notification_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    notification = db.get(AdminNotification, notification_id)
    if notification is None or notification.recipient_id != actor.id:
        raise HTTPException(status_code=404, detail="Notification not found")
    notification.is_read = True
    record_audit(db, actor, "notification.read", "admin_notification", notification_id)
    db.commit()
    return {"status": "read"}


@router.post("/api/v1/knowledge-hub", status_code=201, response_model=KnowledgeRead)
def create_knowledge(
    payload: KnowledgeInput,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(Permission.edit_process_articles)),
):
    needs_approval = actor.role == UserRole.operator
    article = KnowledgeArticle(
        **payload.model_dump(exclude={"is_active", "expected_updated_at"}),
        is_active=False if needs_approval else payload.is_active,
        approval_status="pending" if needs_approval else "approved",
        approved_by_id=None if needs_approval else actor.id,
        approved_at=None if needs_approval else utc_now(),
        created_by_id=actor.id,
    )
    db.add(article)
    db.flush()
    record_audit(db, actor, "knowledge.created", "knowledge_article", article.id)
    if needs_approval:
        admins = db.scalars(
            select(User).where(User.role == UserRole.admin, User.is_active.is_(True))
        ).all()
        for admin in admins:
            db.add(AdminNotification(
                recipient_id=admin.id,
                article_id=article.id,
                message=f"{actor.full_name} submitted a Knowledge Hub post for approval: {article.issue_title}",
            ))
    db.commit()
    db.refresh(article)
    return article


@router.put("/api/v1/knowledge-hub/{article_id}", response_model=KnowledgeRead)
def update_knowledge(
    article_id: int,
    payload: KnowledgeInput,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(Permission.edit_process_articles)),
):
    article = db.get(KnowledgeArticle, article_id)
    if article is None:
        raise HTTPException(status_code=404, detail="Knowledge article not found")
    if payload.expected_updated_at is None:
        raise HTTPException(
            status_code=428,
            detail="Reload this knowledge article before editing so the latest version is included.",
        )
    locked_at = utc_now()
    claim = db.execute(
        update(KnowledgeArticle)
        .where(
            KnowledgeArticle.id == article.id,
            KnowledgeArticle.updated_at == payload.expected_updated_at,
        )
        .values(updated_at=locked_at)
        .execution_options(synchronize_session=False)
    )
    if claim.rowcount != 1:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="This knowledge article changed after you opened it. Reload it before saving again.",
        )
    article.updated_at = locked_at
    needs_approval = actor.role == UserRole.operator
    for key, value in payload.model_dump(exclude={"is_active", "expected_updated_at"}).items():
        setattr(article, key, value)
    if needs_approval:
        article.is_active = False
        article.approval_status = "pending"
        article.approved_by_id = None
        article.approved_at = None
        admins = db.scalars(
            select(User).where(User.role == UserRole.admin, User.is_active.is_(True))
        ).all()
        for admin in admins:
            db.add(AdminNotification(
                recipient_id=admin.id,
                article_id=article.id,
                message=f"{actor.full_name} updated a Knowledge Hub post and submitted it for approval: {article.issue_title}",
            ))
    else:
        article.is_active = payload.is_active
        article.approval_status = "approved"
        article.approved_by_id = actor.id
        article.approved_at = utc_now()
    record_audit(db, actor, "knowledge.updated", "knowledge_article", article.id)
    db.commit()
    db.refresh(article)
    return article


@router.post("/api/v1/knowledge-hub/{article_id}/approve", response_model=KnowledgeRead)
def approve_knowledge(
    article_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.admin)),
):
    article = db.get(KnowledgeArticle, article_id)
    if article is None:
        raise HTTPException(status_code=404, detail="Knowledge article not found")
    if article.approval_status != "pending":
        raise HTTPException(status_code=409, detail="Knowledge article is not pending approval")
    article.approval_status = "approved"
    article.is_active = True
    article.approved_by_id = actor.id
    article.approved_at = utc_now()
    db.execute(
        update(AdminNotification)
        .where(AdminNotification.article_id == article.id)
        .values(is_read=True)
    )
    record_audit(db, actor, "knowledge.approved", "knowledge_article", article.id)
    db.commit()
    db.refresh(article)
    return article


@router.post("/api/v1/knowledge-hub/{article_id}/reject", response_model=KnowledgeRead)
def reject_knowledge(
    article_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.admin)),
):
    article = db.get(KnowledgeArticle, article_id)
    if article is None:
        raise HTTPException(status_code=404, detail="Knowledge article not found")
    if article.approval_status != "pending":
        raise HTTPException(status_code=409, detail="Knowledge article is not pending approval")
    article.approval_status = "rejected"
    article.is_active = False
    db.execute(
        update(AdminNotification)
        .where(AdminNotification.article_id == article.id)
        .values(is_read=True)
    )
    record_audit(db, actor, "knowledge.rejected", "knowledge_article", article.id)
    db.commit()
    db.refresh(article)
    return article
