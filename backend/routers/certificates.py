from typing import Literal

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from db import get_db
from deps import Actor, err, get_actor
from services import certificates as svc
from services.issuance import bulk_issue

router = APIRouter(prefix="/api/certificates", tags=["certificates"])

SortField = Literal["issued_local_date", "learner_name", "serial", "course_title", "status"]
SortDir = Literal["asc", "desc"]


class BulkIssueIn(BaseModel):
    course_id: int


@router.get("")
def list_certificates(
    q: str = "",
    sort: SortField = "issued_local_date",
    direction: SortDir = Query("desc", alias="dir"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    actor: Actor = Depends(get_actor),
    conn=Depends(get_db),
):
    items, total = svc.list_certificates(conn, actor, q, sort, direction, page, page_size)
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/export.csv")
def export_csv(
    q: str = "",
    sort: SortField = "issued_local_date",
    direction: SortDir = Query("desc", alias="dir"),
    actor: Actor = Depends(get_actor),
):
    return StreamingResponse(
        svc.iter_csv(actor, q, sort, direction),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="certificates.csv"'},
    )


@router.post("/bulk-issue")
def bulk_issue_endpoint(
    body: BulkIssueIn,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    actor: Actor = Depends(get_actor),
    conn=Depends(get_db),
):
    if not idempotency_key or not idempotency_key.strip():
        raise err(400, "idempotency_key_required", "Idempotency-Key header is required")
    return bulk_issue(conn, actor, body.course_id, idempotency_key.strip())


@router.get("/{cert_id}")
def get_certificate(cert_id: int, actor: Actor = Depends(get_actor), conn=Depends(get_db)):
    item = svc.get_detail(conn, actor, cert_id)
    if not item:
        raise err(404, "certificate_not_found", f"certificate {cert_id} not found")
    return item


@router.post("/{cert_id}/revoke")
def revoke_certificate(cert_id: int, actor: Actor = Depends(get_actor), conn=Depends(get_db)):
    item = svc.revoke(conn, actor, cert_id)
    if not item:
        raise err(404, "certificate_not_found", f"certificate {cert_id} not found")
    return item
