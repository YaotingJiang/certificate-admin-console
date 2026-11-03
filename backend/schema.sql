CREATE TABLE IF NOT EXISTS tenants (
    id        INTEGER PRIMARY KEY,
    code      TEXT NOT NULL UNIQUE,
    name      TEXT NOT NULL,
    timezone  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS admins (
    id        INTEGER PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id),
    email     TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS learners (
    id        INTEGER PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id),
    name      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS courses (
    id        INTEGER PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id),
    title     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS enrollments (
    id               INTEGER PRIMARY KEY,
    tenant_id        INTEGER NOT NULL REFERENCES tenants(id),
    learner_id       INTEGER NOT NULL REFERENCES learners(id),
    course_id        INTEGER NOT NULL REFERENCES courses(id),
    completed_at_utc TEXT,
    UNIQUE (learner_id, course_id)
);
CREATE INDEX IF NOT EXISTS ix_enrollments_course ON enrollments(course_id);

CREATE TABLE IF NOT EXISTS certificates (
    id                INTEGER PRIMARY KEY,
    tenant_id         INTEGER NOT NULL REFERENCES tenants(id),
    enrollment_id     INTEGER NOT NULL UNIQUE REFERENCES enrollments(id),
    learner_id        INTEGER NOT NULL REFERENCES learners(id),
    course_id         INTEGER NOT NULL REFERENCES courses(id),
    learner_name      TEXT NOT NULL,
    course_title      TEXT NOT NULL,
    serial            TEXT NOT NULL UNIQUE,
    status            TEXT NOT NULL CHECK (status IN ('active', 'revoked')),
    issued_at_utc     TEXT NOT NULL,
    issued_local_date TEXT NOT NULL,
    revoked_at_utc    TEXT
);
CREATE INDEX IF NOT EXISTS ix_certificates_tenant_date    ON certificates(tenant_id, issued_local_date, id);
CREATE INDEX IF NOT EXISTS ix_certificates_tenant_learner ON certificates(tenant_id, learner_name, id);
CREATE INDEX IF NOT EXISTS ix_certificates_tenant_serial  ON certificates(tenant_id, serial);

CREATE TABLE IF NOT EXISTS audit_events (
    id             INTEGER PRIMARY KEY,
    tenant_id      INTEGER NOT NULL REFERENCES tenants(id),
    actor_id       INTEGER NOT NULL REFERENCES admins(id),
    action         TEXT NOT NULL CHECK (action IN ('certificate.issued', 'certificate.revoked')),
    certificate_id INTEGER NOT NULL REFERENCES certificates(id),
    operation_id   TEXT,
    created_at_utc TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_audit_certificate ON audit_events(certificate_id);

CREATE TABLE IF NOT EXISTS idempotency_keys (
    tenant_id      INTEGER NOT NULL REFERENCES tenants(id),
    key            TEXT NOT NULL,
    request_hash   TEXT NOT NULL,
    status         TEXT NOT NULL CHECK (status IN ('in_progress', 'done')),
    response_json  TEXT,
    created_at_utc TEXT NOT NULL,
    PRIMARY KEY (tenant_id, key)
);
