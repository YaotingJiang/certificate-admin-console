from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException

from db import get_db


@dataclass
class Actor:
    id: int
    email: str
    tenant_id: int
    tenant_code: str
    tenant_name: str
    tz: str


def err(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


def get_actor(
    x_actor: str | None = Header(default=None, alias="X-Actor"),
    conn=Depends(get_db),
) -> Actor:
    """Actor identity comes only from the X-Actor header; everything downstream is scoped to actor.tenant_id."""
    if not x_actor:
        raise err(401, "actor_required", "X-Actor header is required (e.g. alice@east.test)")
    row = conn.execute(
        """SELECT a.id, a.email, t.id AS tenant_id, t.code, t.name, t.timezone
           FROM admins a JOIN tenants t ON t.id = a.tenant_id WHERE a.email = ?""",
        (x_actor.strip().lower(),),
    ).fetchone()
    if not row:
        raise err(401, "unknown_actor", f"no admin with email {x_actor!r}")
    return Actor(row["id"], row["email"], row["tenant_id"], row["code"], row["name"], row["timezone"])
