from fastapi import APIRouter, Depends

from db import get_db
from deps import Actor, get_actor

router = APIRouter(prefix="/api", tags=["actors"])


@router.get("/actors")
def list_actors(conn=Depends(get_db)):
    """Demo-only: the seeded admins, so the UI can pick an actor (no login per the brief)."""
    rows = conn.execute(
        "SELECT a.email, t.code AS tenant_code FROM admins a JOIN tenants t ON t.id = a.tenant_id ORDER BY a.email"
    ).fetchall()
    return [dict(r) for r in rows]


@router.get("/me")
def me(actor: Actor = Depends(get_actor)):
    return {"email": actor.email,
            "tenant": {"code": actor.tenant_code, "name": actor.tenant_name, "timezone": actor.tz}}


@router.get("/courses")
def list_courses(actor: Actor = Depends(get_actor), conn=Depends(get_db)):
    rows = conn.execute(
        "SELECT id, title FROM courses WHERE tenant_id = ? ORDER BY title", (actor.tenant_id,)
    ).fetchall()
    return [dict(r) for r in rows]
