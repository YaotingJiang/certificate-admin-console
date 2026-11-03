import hashlib
import json
import sqlite3
import uuid

from db import write_txn
from deps import Actor, err
from tz import now_utc_iso, to_local


def new_serial(tenant_code: str) -> str:
    return f"{tenant_code}-{uuid.uuid4().hex[:10].upper()}"


def issue_certificate(conn, actor: Actor, enrollment_id: int, learner_id: int, course_id: int,
                      learner_name: str, course_title: str, issued_at_utc: str, operation_id: str) -> tuple[int, str]:
    """One certificate + exactly one 'issued' audit event, inside the caller's transaction."""
    serial = new_serial(actor.tenant_code)
    local_date, _ = to_local(issued_at_utc, actor.tz)
    cert_id = conn.execute(
        """INSERT INTO certificates(tenant_id, enrollment_id, learner_id, course_id, learner_name,
               course_title, serial, status, issued_at_utc, issued_local_date)
           VALUES (?,?,?,?,?,?,?,'active',?,?)""",
        (actor.tenant_id, enrollment_id, learner_id, course_id, learner_name, course_title,
         serial, issued_at_utc, local_date),
    ).lastrowid
    conn.execute(
        """INSERT INTO audit_events(tenant_id, actor_id, action, certificate_id, operation_id, created_at_utc)
           VALUES (?,?,'certificate.issued',?,?,?)""",
        (actor.tenant_id, actor.id, cert_id, operation_id, issued_at_utc),
    )
    return cert_id, serial


def bulk_issue(conn, actor: Actor, course_id: int, idempotency_key: str) -> dict:
    """Whole operation is one BEGIN IMMEDIATE transaction keyed by (tenant, idempotency key).

    Concurrent duplicates queue on the write lock; when they get it the key row already exists
    and they replay the stored response (A2). Same key + different payload -> 409 (A3).
    A cross-tenant course -> 404 and the transaction rolls back, so nothing persists (A1).
    """
    request_hash = hashlib.sha256(json.dumps({"course_id": course_id}, sort_keys=True).encode()).hexdigest()
    operation_id = uuid.uuid4().hex
    now = now_utc_iso()

    with write_txn(conn):
        try:
            conn.execute(
                "INSERT INTO idempotency_keys(tenant_id, key, request_hash, status, response_json, created_at_utc) "
                "VALUES (?,?,?,'in_progress',NULL,?)",
                (actor.tenant_id, idempotency_key, request_hash, now),
            )
        except sqlite3.IntegrityError:
            row = conn.execute(
                "SELECT request_hash, status, response_json FROM idempotency_keys WHERE tenant_id = ? AND key = ?",
                (actor.tenant_id, idempotency_key),
            ).fetchone()
            if row["request_hash"] != request_hash:
                raise err(409, "idempotency_key_reused",
                          "Idempotency-Key was already used with a different request payload")
            if row["status"] == "done":
                return {**json.loads(row["response_json"]), "replayed": True}
            raise err(409, "operation_in_progress", "the same operation is still in progress")

        course = conn.execute(
            "SELECT id, title FROM courses WHERE id = ? AND tenant_id = ?", (course_id, actor.tenant_id)
        ).fetchone()
        if not course:
            raise err(404, "course_not_found", f"course {course_id} not found")

        rows = conn.execute(
            """SELECT e.id AS enrollment_id, e.learner_id, l.name AS learner_name, e.completed_at_utc,
                      c.id AS cert_id, c.serial
               FROM enrollments e
               JOIN learners l ON l.id = e.learner_id
               LEFT JOIN certificates c ON c.enrollment_id = e.id
               WHERE e.course_id = ? AND e.tenant_id = ?
               ORDER BY l.name, e.id""",
            (course_id, actor.tenant_id),
        ).fetchall()

        summary = {"issued": 0, "skipped": 0, "failed": 0}
        results = []
        for r in rows:
            serial = None
            if r["cert_id"]:
                outcome, reason, serial = "skipped", "already_certified", r["serial"]
            elif not r["completed_at_utc"]:
                outcome, reason = "skipped", "not_completed"
            else:
                try:
                    _, serial = issue_certificate(conn, actor, r["enrollment_id"], r["learner_id"], course["id"],
                                                  r["learner_name"], course["title"], now, operation_id)
                    outcome, reason = "issued", None
                except sqlite3.IntegrityError as exc:
                    outcome, reason = "failed", f"constraint violation: {exc}"
            summary[outcome] += 1
            results.append({"learner_id": r["learner_id"], "learner_name": r["learner_name"],
                            "outcome": outcome, "reason": reason, "serial": serial})

        response = {
            "operation_id": operation_id,
            "course_id": course["id"],
            "course_title": course["title"],
            "summary": summary,
            "results": results,
            "replayed": False,
        }
        conn.execute(
            "UPDATE idempotency_keys SET status = 'done', response_json = ? WHERE tenant_id = ? AND key = ?",
            (json.dumps(response), actor.tenant_id, idempotency_key),
        )
    return response
