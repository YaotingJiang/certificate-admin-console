"""A1-A7 from the brief. Tests share one seeded temp DB and run in file order."""
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from db import connect
from main import app

ALICE = {"X-Actor": "alice@east.test"}
BOB = {"X-Actor": "bob@west.test"}
CERTS = "/api/certificates"
EXPORT = "/api/certificates/export.csv"


def list_certs(client, headers, **params):
    r = client.get(CERTS, headers=headers, params={"page_size": 100, **params})
    assert r.status_code == 200, r.text
    return r.json()


def find(client, headers, serial):
    items = list_certs(client, headers, q=serial)["items"]
    assert len(items) == 1
    return items[0]


def course_id(client, headers, title):
    return next(c["id"] for c in client.get("/api/courses", headers=headers).json() if c["title"] == title)


def db_count(sql, *params):
    conn = connect()
    try:
        return conn.execute(sql, params).fetchone()[0]
    finally:
        conn.close()


def strip_replayed(body):
    return {k: v for k, v in body.items() if k != "replayed"}


# ---------------------------------------------------------------- A5
def test_a5_dst_and_tenant_local_date(client):
    east = find(client, ALICE, "EAST-SEED-0001")
    west = find(client, BOB, "WEST-SEED-0001")
    assert east["issued_at_utc"] == west["issued_at_utc"] == "2026-01-10T13:30:00Z"
    assert (east["issued_at_local"], east["issued_local_date"]) == ("2026-01-11 00:30", "2026-01-11")
    assert (west["issued_at_local"], west["issued_local_date"]) == ("2026-01-10 21:30", "2026-01-10")
    csv_east = client.get(EXPORT, headers=ALICE, params={"q": "EAST-SEED-0001"}).text
    assert "Jordan Kim,Safety 101,EAST-SEED-0001,2026-01-11" in csv_east
    csv_west = client.get(EXPORT, headers=BOB, params={"q": "WEST-SEED-0001"}).text
    assert "Jordan Kim,Safety 101,WEST-SEED-0001,2026-01-10" in csv_west
    # list sorts by the tenant-local calendar date, ascending => Maria (2026-01-01 Sydney) before Jordan
    items = list_certs(client, ALICE, sort="issued_local_date", dir="asc")["items"]
    dates = [i["issued_local_date"] for i in items]
    assert dates == sorted(dates)


# ---------------------------------------------------------------- A1
def test_a1_tenant_isolation(client):
    west_items = list_certs(client, BOB)["items"]
    assert west_items and all(i["serial"].startswith("WEST-") for i in west_items)
    csv_text = client.get(EXPORT, headers=BOB).text
    assert "WEST-" in csv_text and "EAST-" not in csv_text

    east_cert = find(client, ALICE, "EAST-SEED-0001")
    assert client.get(f"{CERTS}/{east_cert['id']}", headers=BOB).status_code == 404
    assert client.post(f"{CERTS}/{east_cert['id']}/revoke", headers=BOB).status_code == 404
    assert find(client, ALICE, "EAST-SEED-0001")["status"] == "active"

    east_safety = course_id(client, ALICE, "Safety 101")
    certs_before, audit_before = db_count("SELECT COUNT(*) FROM certificates"), db_count("SELECT COUNT(*) FROM audit_events")
    r = client.post(f"{CERTS}/bulk-issue", headers={**BOB, "Idempotency-Key": "bob-cross-tenant"},
                    json={"course_id": east_safety})
    assert r.status_code == 404
    assert db_count("SELECT COUNT(*) FROM certificates") == certs_before
    assert db_count("SELECT COUNT(*) FROM audit_events") == audit_before
    assert db_count("SELECT COUNT(*) FROM idempotency_keys WHERE key='bob-cross-tenant'") == 0

    assert client.get(CERTS).status_code == 401
    assert client.get(CERTS, headers={"X-Actor": "mallory@nowhere.test"}).status_code == 401


# ---------------------------------------------------------------- A2 + A4
KEY = "alice-safety-" + uuid.uuid4().hex
FIRST_RESPONSE = {}


def test_a2_a4_bulk_issue_outcomes_and_retry_safety(client):
    cid = course_id(client, ALICE, "Safety 101")
    headers = {**ALICE, "Idempotency-Key": KEY}

    r1 = client.post(f"{CERTS}/bulk-issue", headers=headers, json={"course_id": cid})
    assert r1.status_code == 200, r1.text
    body = r1.json()
    FIRST_RESPONSE.update(body)
    assert body["replayed"] is False
    assert body["summary"] == {"issued": 2, "skipped": 3, "failed": 0}
    outcomes = {x["learner_name"]: (x["outcome"], x["reason"]) for x in body["results"]}
    assert outcomes == {
        "Alex Lee": ("issued", None),
        "Priya Nair": ("issued", None),
        "Sam Chen": ("skipped", "not_completed"),
        "Jordan Kim": ("skipped", "already_certified"),
        "Maria Garcia": ("skipped", "already_certified"),
    }

    # sequential retry
    r2 = client.post(f"{CERTS}/bulk-issue", headers=headers, json={"course_id": cid})
    assert r2.status_code == 200 and r2.json()["replayed"] is True
    assert strip_replayed(r2.json()) == strip_replayed(body)

    # concurrent retries: each thread gets its own client (own connection)
    def call(_):
        return TestClient(app).post(f"{CERTS}/bulk-issue", headers=headers, json={"course_id": cid})

    with ThreadPoolExecutor(max_workers=8) as ex:
        responses = list(ex.map(call, range(8)))
    assert all(r.status_code == 200 for r in responses), [r.text for r in responses]
    assert all(strip_replayed(r.json()) == strip_replayed(body) for r in responses)

    assert db_count("SELECT COUNT(*) FROM certificates WHERE course_id=?", cid) == 4  # 2 seeded + 2 issued
    assert db_count("SELECT COUNT(*) FROM audit_events WHERE operation_id=?", body["operation_id"]) == 2
    assert db_count(
        "SELECT COUNT(*) FROM (SELECT certificate_id FROM audit_events WHERE action='certificate.issued' "
        "GROUP BY certificate_id HAVING COUNT(*) > 1)") == 0


# ---------------------------------------------------------------- A3
def test_a3_key_reuse_with_different_payload(client):
    other = course_id(client, ALICE, "Data Privacy Basics")
    before = db_count("SELECT COUNT(*) FROM certificates")
    r = client.post(f"{CERTS}/bulk-issue", headers={**ALICE, "Idempotency-Key": KEY}, json={"course_id": other})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "idempotency_key_reused"
    assert db_count("SELECT COUNT(*) FROM certificates") == before
    # first result untouched
    r2 = client.post(f"{CERTS}/bulk-issue", headers={**ALICE, "Idempotency-Key": KEY},
                     json={"course_id": FIRST_RESPONSE["course_id"]})
    assert strip_replayed(r2.json()) == strip_replayed(FIRST_RESPONSE)
    # missing key
    assert client.post(f"{CERTS}/bulk-issue", headers=ALICE, json={"course_id": other}).status_code == 400


# ---------------------------------------------------------------- A7
def test_a7_revocation_audit_once(client):
    serial = next(x["serial"] for x in FIRST_RESPONSE["results"] if x["learner_name"] == "Alex Lee")
    cert = find(client, ALICE, serial)
    r1 = client.post(f"{CERTS}/{cert['id']}/revoke", headers=ALICE)
    assert r1.status_code == 200 and r1.json()["status"] == "revoked"
    r2 = client.post(f"{CERTS}/{cert['id']}/revoke", headers=ALICE)
    assert r2.status_code == 200 and r2.json()["status"] == "revoked"
    revocations = [a for a in r2.json()["audit"] if a["action"] == "certificate.revoked"]
    issuances = [a for a in r2.json()["audit"] if a["action"] == "certificate.issued"]
    assert len(revocations) == 1 and len(issuances) == 1
    assert revocations[0]["actor_email"] == "alice@east.test"


def test_revoked_certificate_is_not_reissued_by_bulk(client):
    """After A7, Alex Lee's Safety 101 certificate is revoked. Bulk issue must not re-issue it,
    and must say why (distinct from already_certified)."""
    cid = course_id(client, ALICE, "Safety 101")
    before = db_count("SELECT COUNT(*) FROM certificates WHERE course_id=?", cid)
    r = client.post(f"{CERTS}/bulk-issue", headers={**ALICE, "Idempotency-Key": "after-revoke-" + uuid.uuid4().hex},
                    json={"course_id": cid})
    assert r.status_code == 200
    body = r.json()
    assert body["summary"]["issued"] == 0
    alex = next(x for x in body["results"] if x["learner_name"] == "Alex Lee")
    assert (alex["outcome"], alex["reason"]) == ("skipped", "certificate_revoked")
    priya = next(x for x in body["results"] if x["learner_name"] == "Priya Nair")
    assert (priya["outcome"], priya["reason"]) == ("skipped", "already_certified")
    assert db_count("SELECT COUNT(*) FROM certificates WHERE course_id=?", cid) == before


# ---------------------------------------------------------------- list UX basics
def test_list_search_sort_paginate(client):
    page1 = list_certs(client, ALICE, page=1, page_size=2, sort="serial", dir="asc")
    page2 = list_certs(client, ALICE, page=2, page_size=2, sort="serial", dir="asc")
    assert page1["total"] >= 4 and len(page1["items"]) == 2 and len(page2["items"]) == 2
    serials = [i["serial"] for i in page1["items"] + page2["items"]]
    assert serials == sorted(serials)
    assert list_certs(client, ALICE, q="Alex")["items"][0]["learner_name"] == "Alex Lee"
    assert list_certs(client, ALICE, q="zzz-nothing")["items"] == []
    assert client.get(CERTS, headers=ALICE, params={"sort": "id; DROP"}).status_code == 422


# ---------------------------------------------------------------- A6 (opt-in: pytest -m big)
@pytest.mark.big
def test_a6_export_growth(client):
    from seed import seed_big

    conn = connect()
    try:
        seed_big(conn, "EAST", 100_000)
    finally:
        conn.close()
    params = {"q": "Lee", "sort": "learner_name", "dir": "asc"}
    expected_total = list_certs(client, ALICE, **params)["total"]
    assert expected_total > 1000

    list_ok = {}

    def list_during_export():
        time.sleep(0.2)
        r = TestClient(app).get(CERTS, headers=ALICE, params={**params, "page": 3})
        list_ok["status"] = r.status_code
        list_ok["elapsed"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    probe = threading.Thread(target=list_during_export)
    probe.start()
    first = client.get(EXPORT, headers=ALICE, params=params)
    t_first = time.perf_counter() - t0
    probe.join()
    t0 = time.perf_counter()
    second = client.get(EXPORT, headers=ALICE, params=params)
    t_second = time.perf_counter() - t0

    assert first.status_code == 200 and second.status_code == 200
    assert t_first < 60 and t_second < 60, (t_first, t_second)
    assert list_ok["status"] == 200
    assert first.content == second.content  # equal sort keys keep relative order (id tiebreak)
    lines = first.text.splitlines()
    assert lines[0] == "learner_name,course_title,serial,issued_local_date"
    rows = [ln.split(",") for ln in lines[1:]]
    assert len(rows) == expected_total
    assert all("Lee" in r[0] or "Lee" in r[2] for r in rows)
    assert all(r[2].startswith("EAST-") for r in rows)
    names = [r[0] for r in rows]
    assert names == sorted(names)
    print(f"\nA6: {len(rows)} rows, export #1 {t_first:.2f}s, #2 {t_second:.2f}s, "
          f"list during export -> {list_ok['status']} after {list_ok['elapsed']:.2f}s")
