"""Demo data.

    python seed.py                           quick-start dataset (idempotent: no-op if tenants exist)
    python seed.py --big EAST --rows 100000  append generated certificates to one tenant (A6).
                                             Never touches the quick-start rows; refuses to run twice.
"""
import argparse
import random
import sys
from datetime import timedelta

from db import connect, init_schema, write_txn
from tz import UTC_FMT, parse_utc, to_local

A5_UTC = "2026-01-10T13:30:00Z"

TENANTS = [
    ("EAST", "East", "Australia/Sydney", "alice@east.test"),
    ("WEST", "West", "Australia/Perth", "bob@west.test"),
]
LEARNERS = ["Alex Lee", "Priya Nair", "Sam Chen", "Jordan Kim", "Maria Garcia", "Tom Walsh"]

FIRST = ["Alex", "Priya", "Sam", "Jordan", "Maria", "Tom", "Wei", "Aisha", "Noah", "Olivia", "Liam", "Mia"]
LAST = ["Lee", "Nair", "Chen", "Kim", "Garcia", "Walsh", "Singh", "Nguyen", "Brown", "Patel"]


def _issue(conn, tenant_id, actor_id, enrollment_id, learner_id, course_id, learner_name,
           course_title, serial, issued_at_utc, tz_name):
    local_date, _ = to_local(issued_at_utc, tz_name)
    cert_id = conn.execute(
        """INSERT INTO certificates(tenant_id, enrollment_id, learner_id, course_id, learner_name,
               course_title, serial, status, issued_at_utc, issued_local_date)
           VALUES (?,?,?,?,?,?,?,'active',?,?)""",
        (tenant_id, enrollment_id, learner_id, course_id, learner_name, course_title, serial,
         issued_at_utc, local_date),
    ).lastrowid
    conn.execute(
        """INSERT INTO audit_events(tenant_id, actor_id, action, certificate_id, operation_id, created_at_utc)
           VALUES (?,?,'certificate.issued',?,?,?)""",
        (tenant_id, actor_id, cert_id, "seed", issued_at_utc),
    )
    return cert_id


def seed_quick(conn) -> bool:
    if conn.execute("SELECT COUNT(*) FROM tenants").fetchone()[0]:
        return False
    with write_txn(conn):
        for code, name, tz_name, admin_email in TENANTS:
            tid = conn.execute("INSERT INTO tenants(code,name,timezone) VALUES (?,?,?)", (code, name, tz_name)).lastrowid
            aid = conn.execute("INSERT INTO admins(tenant_id,email) VALUES (?,?)", (tid, admin_email)).lastrowid
            L = {n: conn.execute("INSERT INTO learners(tenant_id,name) VALUES (?,?)", (tid, n)).lastrowid for n in LEARNERS}
            safety = conn.execute("INSERT INTO courses(tenant_id,title) VALUES (?,?)", (tid, "Safety 101")).lastrowid
            privacy = conn.execute("INSERT INTO courses(tenant_id,title) VALUES (?,?)", (tid, "Data Privacy Basics")).lastrowid

            def enroll(learner, course, completed):
                return conn.execute(
                    "INSERT INTO enrollments(tenant_id,learner_id,course_id,completed_at_utc) VALUES (?,?,?,?)",
                    (tid, L[learner], course, completed),
                ).lastrowid

            # Safety 101: eligible, eligible, incomplete, certified (A5 timestamp), certified
            enroll("Alex Lee", safety, "2026-02-01T02:00:00Z")
            enroll("Priya Nair", safety, "2026-02-02T03:00:00Z")
            enroll("Sam Chen", safety, None)
            e = enroll("Jordan Kim", safety, "2026-01-09T01:00:00Z")
            _issue(conn, tid, aid, e, L["Jordan Kim"], safety, "Jordan Kim", "Safety 101", f"{code}-SEED-0001", A5_UTC, tz_name)
            e = enroll("Maria Garcia", safety, "2025-12-30T01:00:00Z")
            _issue(conn, tid, aid, e, L["Maria Garcia"], safety, "Maria Garcia", "Safety 101", f"{code}-SEED-0002", "2025-12-31T14:00:00Z", tz_name)

            # Data Privacy Basics: eligible, incomplete, certified
            enroll("Alex Lee", privacy, "2026-02-03T04:00:00Z")
            enroll("Sam Chen", privacy, None)
            e = enroll("Tom Walsh", privacy, "2026-01-20T00:00:00Z")
            _issue(conn, tid, aid, e, L["Tom Walsh"], privacy, "Tom Walsh", "Data Privacy Basics", f"{code}-SEED-0003", "2026-01-20T05:00:00Z", tz_name)
    return True


def seed_big(conn, tenant_code: str, rows: int, seed: int = 42) -> None:
    t = conn.execute("SELECT id, timezone FROM tenants WHERE code=?", (tenant_code,)).fetchone()
    if not t:
        sys.exit(f"unknown tenant {tenant_code}")
    tid, tz_name = t["id"], t["timezone"]
    aid = conn.execute("SELECT id FROM admins WHERE tenant_id=?", (tid,)).fetchone()["id"]
    if conn.execute("SELECT 1 FROM courses WHERE tenant_id=? AND title LIKE 'Bulk Course %'", (tid,)).fetchone():
        sys.exit(f"{tenant_code} already has generated data; delete the DB to regenerate")

    rnd = random.Random(seed)
    n_courses = 20
    n_learners = -(-rows // n_courses)  # ceil
    names = [f"{f} {l}" for f in FIRST for l in LAST]  # 120 names -> heavy key repetition
    base = parse_utc("2025-06-01T00:00:00Z")

    def next_id(table):
        return (conn.execute(f"SELECT COALESCE(MAX(id),0) FROM {table}").fetchone()[0]) + 1

    with write_txn(conn):
        course_ids = [
            conn.execute("INSERT INTO courses(tenant_id,title) VALUES (?,?)", (tid, f"Bulk Course {i:02d}")).lastrowid
            for i in range(1, n_courses + 1)
        ]
        l0 = next_id("learners")
        learner_rows = [(l0 + i, tid, names[i % len(names)]) for i in range(n_learners)]
        conn.executemany("INSERT INTO learners(id,tenant_id,name) VALUES (?,?,?)", learner_rows)

        e0, c0, a0 = next_id("enrollments"), next_id("certificates"), next_id("audit_events")
        enrolls, certs, audits = [], [], []
        for i in range(rows):
            li, ci = i % n_learners, i // n_learners
            learner_id, learner_name = learner_rows[li][0], learner_rows[li][2]
            course_id = course_ids[ci]
            issued_dt = base + timedelta(seconds=rnd.randrange(0, 200 * 86400))
            issued_utc = issued_dt.strftime(UTC_FMT)
            local_date, _ = to_local(issued_utc, tz_name)
            status = "revoked" if i % 50 == 0 else "active"
            enrolls.append((e0 + i, tid, learner_id, course_id, issued_utc))
            certs.append((c0 + i, tid, e0 + i, learner_id, course_id, learner_name, f"Bulk Course {ci + 1:02d}",
                          f"{tenant_code}-G{i + 1:07d}", status, issued_utc, local_date,
                          issued_utc if status == "revoked" else None))
            audits.append((a0 + i, tid, aid, "certificate.issued", c0 + i, "generator", issued_utc))
        conn.executemany("INSERT INTO enrollments(id,tenant_id,learner_id,course_id,completed_at_utc) VALUES (?,?,?,?,?)", enrolls)
        conn.executemany(
            """INSERT INTO certificates(id,tenant_id,enrollment_id,learner_id,course_id,learner_name,course_title,
               serial,status,issued_at_utc,issued_local_date,revoked_at_utc) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""", certs)
        conn.executemany(
            "INSERT INTO audit_events(id,tenant_id,actor_id,action,certificate_id,operation_id,created_at_utc) VALUES (?,?,?,?,?,?,?)",
            audits)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--big", metavar="TENANT_CODE", help="append generated certificates to this tenant")
    ap.add_argument("--rows", type=int, default=100_000)
    args = ap.parse_args()
    conn = connect()
    init_schema(conn)
    created = seed_quick(conn)
    print("quick-start data:", "created" if created else "already present")
    if args.big:
        seed_big(conn, args.big.upper(), args.rows)
        print(f"generated {args.rows} certificates for {args.big.upper()}")


if __name__ == "__main__":
    main()
