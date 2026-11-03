import csv
import io
import sqlite3

from db import connect, write_txn
from deps import Actor
from tz import now_utc_iso, to_local

SORT_COLUMNS = ("issued_local_date", "learner_name", "serial", "course_title", "status")
EXPORT_BATCH = 2000


def _where(tenant_id: int, q: str) -> tuple[str, list]:
    sql, params = "tenant_id = ?", [tenant_id]
    q = (q or "").strip()
    if q:
        like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        sql += " AND (learner_name LIKE ? ESCAPE '\\' OR serial LIKE ? ESCAPE '\\')"
        params += [like, like]
    return sql, params


def _order(sort: str, direction: str) -> str:
    """Whitelisted column + id tiebreak => total order, so equal keys are stable across runs (A6)."""
    col = sort if sort in SORT_COLUMNS else "issued_local_date"
    d = "ASC" if direction == "asc" else "DESC"
    return f"{col} {d}, id ASC"


def to_item(row: sqlite3.Row, tz_name: str) -> dict:
    local_date, local_display = to_local(row["issued_at_utc"], tz_name)
    return {
        "id": row["id"],
        "serial": row["serial"],
        "learner_name": row["learner_name"],
        "course_title": row["course_title"],
        "status": row["status"],
        "issued_at_utc": row["issued_at_utc"],
        "issued_at_local": local_display,
        "issued_local_date": local_date,
        "revoked_at_utc": row["revoked_at_utc"],
    }


def list_certificates(conn, actor: Actor, q: str, sort: str, direction: str, page: int, page_size: int):
    where, params = _where(actor.tenant_id, q)
    total = conn.execute(f"SELECT COUNT(*) FROM certificates WHERE {where}", params).fetchone()[0]
    rows = conn.execute(
        f"SELECT * FROM certificates WHERE {where} ORDER BY {_order(sort, direction)} LIMIT ? OFFSET ?",
        [*params, page_size, (page - 1) * page_size],
    ).fetchall()
    return [to_item(r, actor.tz) for r in rows], total


def iter_csv(actor: Actor, q: str, sort: str, direction: str):
    """Streams CSV in chunks from a single ordered cursor. Opens its own connection because the
    generator runs in a worker thread after the request's dependency connection is closed."""
    where, params = _where(actor.tenant_id, q)
    conn = connect()
    try:
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["learner_name", "course_title", "serial", "issued_local_date"])
        yield buf.getvalue()
        buf.seek(0)
        buf.truncate()
        cur = conn.execute(
            f"SELECT learner_name, course_title, serial, issued_local_date FROM certificates "
            f"WHERE {where} ORDER BY {_order(sort, direction)}",
            params,
        )
        while True:
            rows = cur.fetchmany(EXPORT_BATCH)
            if not rows:
                break
            writer.writerows(tuple(r) for r in rows)
            yield buf.getvalue()
            buf.seek(0)
            buf.truncate()
    finally:
        conn.close()


def get_detail(conn, actor: Actor, cert_id: int) -> dict | None:
    row = conn.execute(
        "SELECT * FROM certificates WHERE id = ? AND tenant_id = ?", (cert_id, actor.tenant_id)
    ).fetchone()
    if not row:
        return None
    audit = conn.execute(
        """SELECT e.id, e.action, a.email AS actor_email, e.operation_id, e.created_at_utc
           FROM audit_events e JOIN admins a ON a.id = e.actor_id
           WHERE e.certificate_id = ? ORDER BY e.id""",
        (cert_id,),
    ).fetchall()
    item = to_item(row, actor.tz)
    item["tenant"] = {"code": actor.tenant_code, "name": actor.tenant_name, "timezone": actor.tz}
    item["audit"] = [dict(a) for a in audit]
    return item


def revoke(conn, actor: Actor, cert_id: int) -> dict | None:
    """Conditional UPDATE on status='active': the audit row is written only when a row actually
    transitioned, so a repeated revoke is a no-op with no duplicate audit event (A7)."""
    with write_txn(conn):
        exists = conn.execute(
            "SELECT 1 FROM certificates WHERE id = ? AND tenant_id = ?", (cert_id, actor.tenant_id)
        ).fetchone()
        if not exists:
            return None
        now = now_utc_iso()
        cur = conn.execute(
            "UPDATE certificates SET status = 'revoked', revoked_at_utc = ? "
            "WHERE id = ? AND tenant_id = ? AND status = 'active'",
            (now, cert_id, actor.tenant_id),
        )
        if cur.rowcount == 1:
            conn.execute(
                """INSERT INTO audit_events(tenant_id, actor_id, action, certificate_id, operation_id, created_at_utc)
                   VALUES (?, ?, 'certificate.revoked', ?, NULL, ?)""",
                (actor.tenant_id, actor.id, cert_id, now),
            )
    return get_detail(conn, actor, cert_id)
