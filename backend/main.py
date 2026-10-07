from __future__ import annotations

import sqlite3
import uuid
import os
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator, Literal

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, model_validator

DATABASE_PATH = Path(os.environ.get("ABHILEKH_DB_PATH", Path(__file__).resolve().parent / "data" / "flags.db"))
FlagStatus = Literal["new", "triage", "assigned", "authority_review", "field_visit", "confirmed", "not_confirmed", "closed", "action_taken", "not_illegal"]
AnalystFlagStatus = Literal["new", "triage", "assigned", "authority_review", "field_visit", "confirmed", "not_confirmed", "closed"]
FlagPriority = Literal["low", "normal", "high"]
PortalRole = Literal["analyst", "authority"]
AuthorityOutcome = Literal["action_taken", "not_illegal"]

app = FastAPI(title="Abhilekh Flag Review API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Content-Type", "X-Actor", "X-Role"],
)


class FlagCreate(BaseModel):
    zone_name: str = Field(min_length=2, max_length=120)
    address: str = Field(min_length=2, max_length=240)
    signal_label: str = Field(min_length=2, max_length=100)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    area_hectares: float = Field(gt=0, le=100_000)
    signal_index: int = Field(ge=0, le=100)
    epoch_t0: date
    epoch_t1: date
    evidence_summary: str = Field(min_length=5, max_length=2_000)

    @model_validator(mode="after")
    def validate_epochs(self) -> FlagCreate:
        if self.epoch_t0 >= self.epoch_t1:
            raise ValueError("Epoch T0 must be earlier than Epoch T1.")
        return self


class FlagUpdate(BaseModel):
    status: AnalystFlagStatus | None = None
    priority: FlagPriority | None = None
    assignee: str | None = Field(default=None, max_length=120)


class NoteCreate(BaseModel):
    note: str = Field(min_length=1, max_length=2_000)


class AuthorityDecision(BaseModel):
    outcome: AuthorityOutcome
    comment: str = Field(min_length=3, max_length=2_000)


@contextmanager
def database() -> Iterator[sqlite3.Connection]:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def add_audit_event(
    connection: sqlite3.Connection,
    flag: sqlite3.Row,
    action: str,
    actor: str,
    summary: str,
    *,
    actor_role: str = "system",
    note: str | None = None,
    from_value: str | None = None,
    to_value: str | None = None,
    created_at: str | None = None,
) -> int:
    cursor = connection.execute(
        """INSERT INTO audit_events
              (flag_id, flag_reference, action, actor, actor_role, summary, note, from_value, to_value, created_at)
              VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
          (flag["id"], flag["reference"], action, actor, actor_role, summary, note, from_value, to_value, created_at or utc_now()),
    )
    return int(cursor.lastrowid)


def seed_demo_flags(connection: sqlite3.Connection) -> None:
    if connection.execute("SELECT COUNT(*) FROM flags").fetchone()[0]:
        return
    today = datetime.now(timezone.utc).date()
    samples = [
        {"reference":"NGP-2026-00127","zone_name":"Laxmi Nagar · Zone 1","address":"North of Ring Road, parcel sector 04","signal_label":"Built-surface gain","latitude":21.1215,"longitude":79.0645,"area_hectares":0.14,"signal_index":78,"epoch_t0":today-timedelta(days=365),"epoch_t1":today-timedelta(days=12),"evidence_summary":"Illustrative spectral signal: built-surface index rose while vegetation index declined. Review cloud cover, alignment, and site history before routing.","status":"triage","priority":"high","assignee":"R. Mehta","age_days":1},
        {"reference":"NGP-2026-00126","zone_name":"Dharampeth · Zone 2","address":"Near Civil Lines connector, block 11","signal_label":"Land-clearing candidate","latitude":21.1438,"longitude":79.0621,"area_hectares":0.08,"signal_index":61,"epoch_t0":today-timedelta(days=340),"epoch_t1":today-timedelta(days=9),"evidence_summary":"Illustrative vegetation-loss signal across two scenes. Seasonal change and temporary site preparation remain possible explanations.","status":"new","priority":"normal","assignee":None,"age_days":2},
        {"reference":"NGP-2026-00119","zone_name":"Dhantoli · Zone 4","address":"South-east grid, ward parcel 7B","signal_label":"Built-surface gain","latitude":21.1405,"longitude":79.0838,"area_hectares":0.23,"signal_index":84,"epoch_t0":today-timedelta(days=365),"epoch_t1":today-timedelta(days=28),"evidence_summary":"Illustrative change candidate routed for permit verification. This record is seeded demo data, not an observed violation.","status":"authority_review","priority":"high","assignee":"Municipal review desk","age_days":4},
        {"reference":"NGP-2026-00108","zone_name":"Nehru Nagar · Zone 5","address":"Central residential grid, lane 2","signal_label":"SAR-supported change","latitude":21.1284,"longitude":79.1176,"area_hectares":0.11,"signal_index":55,"epoch_t0":today-timedelta(days=180),"epoch_t1":today-timedelta(days=18),"evidence_summary":"Illustrative paired-scene signal awaiting a field visit. SAR change is a screening proxy and does not measure building height.","status":"field_visit","priority":"normal","assignee":"S. Deshmukh","age_days":7},
        {"reference":"NGP-2026-00098","zone_name":"Mangalwari · Zone 10","address":"Market approach, sector 3A","signal_label":"Land-clearing candidate","latitude":21.1764,"longitude":79.0718,"area_hectares":0.05,"signal_index":34,"epoch_t0":today-timedelta(days=365),"epoch_t1":today-timedelta(days=45),"evidence_summary":"Illustrative record closed as not confirmed in the demo workflow. This is not a real authority determination.","status":"not_confirmed","priority":"low","assignee":"Municipal review desk","age_days":12},
    ]
    for sample in samples:
        created_at = (datetime.now(timezone.utc) - timedelta(days=sample["age_days"])).isoformat(timespec="seconds").replace("+00:00", "Z")
        flag_id = str(uuid.uuid4())
        connection.execute(
            """INSERT INTO flags
               (id, reference, zone_name, address, signal_label, latitude, longitude, area_hectares,
                signal_index, epoch_t0, epoch_t1, evidence_summary, status, priority, assignee, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (flag_id,sample["reference"],sample["zone_name"],sample["address"],sample["signal_label"],sample["latitude"],sample["longitude"],sample["area_hectares"],sample["signal_index"],sample["epoch_t0"].isoformat(),sample["epoch_t1"].isoformat(),sample["evidence_summary"],sample["status"],sample["priority"],sample["assignee"],created_at,created_at),
        )
        flag = connection.execute("SELECT * FROM flags WHERE id = ?", (flag_id,)).fetchone()
        add_audit_event(connection, flag, "FLAG_CREATED", "Screening demo", "Flag created from illustrative screening data", created_at=created_at)
        if sample["status"] != "new":
            add_audit_event(connection, flag, "STATUS_CHANGED", sample["assignee"] or "Demo analyst", f"Seeded demo status: {sample['status'].replace('_', ' ')}", from_value="new", to_value=sample["status"], created_at=created_at)


def initialize_database() -> None:
    with database() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS flags (
                id TEXT PRIMARY KEY, reference TEXT NOT NULL UNIQUE, zone_name TEXT NOT NULL,
                address TEXT NOT NULL, signal_label TEXT NOT NULL, latitude REAL NOT NULL,
                longitude REAL NOT NULL, area_hectares REAL NOT NULL CHECK (area_hectares > 0),
                signal_index INTEGER NOT NULL CHECK (signal_index BETWEEN 0 AND 100),
                epoch_t0 TEXT NOT NULL, epoch_t1 TEXT NOT NULL, evidence_summary TEXT NOT NULL,
                corporation_name TEXT NOT NULL DEFAULT 'Nagpur Municipal Corporation',
                status TEXT NOT NULL, priority TEXT NOT NULL, assignee TEXT,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT, flag_id TEXT NOT NULL REFERENCES flags(id),
                flag_reference TEXT NOT NULL, action TEXT NOT NULL, actor TEXT NOT NULL,
                actor_role TEXT NOT NULL DEFAULT 'system',
                summary TEXT NOT NULL, note TEXT, from_value TEXT, to_value TEXT, created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_flags_status ON flags(status);
            CREATE INDEX IF NOT EXISTS idx_audit_flag_created ON audit_events(flag_id, created_at DESC);
            CREATE TRIGGER IF NOT EXISTS audit_events_no_update BEFORE UPDATE ON audit_events BEGIN
                SELECT RAISE(ABORT, 'Audit events are append-only'); END;
            CREATE TRIGGER IF NOT EXISTS audit_events_no_delete BEFORE DELETE ON audit_events BEGIN
                SELECT RAISE(ABORT, 'Audit events are append-only'); END;
            """
        )
        flag_columns = {row["name"] for row in connection.execute("PRAGMA table_info(flags)")}
        if "corporation_name" not in flag_columns:
            connection.execute("ALTER TABLE flags ADD COLUMN corporation_name TEXT NOT NULL DEFAULT 'Nagpur Municipal Corporation'")
        audit_columns = {row["name"] for row in connection.execute("PRAGMA table_info(audit_events)")}
        if "actor_role" not in audit_columns:
            connection.execute("ALTER TABLE audit_events ADD COLUMN actor_role TEXT NOT NULL DEFAULT 'analyst'")
        seed_demo_flags(connection)


initialize_database()


def row_to_dict(row: sqlite3.Row) -> dict[str, object]:
    return dict(row)


def get_flag(connection: sqlite3.Connection, flag_id: str) -> sqlite3.Row:
    row = connection.execute("SELECT * FROM flags WHERE id = ?", (flag_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Flag not found.")
    return row


def audit_rows(connection: sqlite3.Connection, flag_id: str | None = None) -> list[dict[str, object]]:
    if flag_id is None:
        rows = connection.execute("SELECT * FROM audit_events ORDER BY created_at DESC, id DESC LIMIT 500").fetchall()
    else:
        rows = connection.execute("SELECT * FROM audit_events WHERE flag_id = ? ORDER BY created_at DESC, id DESC", (flag_id,)).fetchall()
    return [row_to_dict(row) for row in rows]


def require_role(actual: str, expected: PortalRole) -> None:
    if actual != expected:
        raise HTTPException(status_code=403, detail=f"This action requires the {expected} portal role.")


def require_authority_case(flag: sqlite3.Row) -> None:
    if flag["status"] not in {"authority_review", "field_visit", "action_taken", "not_illegal"}:
        raise HTTPException(status_code=404, detail="Flag has not been referred to the authority portal.")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "abhilekh-api"}


@app.get("/api/flags")
def list_flags(x_role: str = Header(default="analyst", alias="X-Role")) -> list[dict[str, object]]:
    require_role(x_role, "analyst")
    with database() as connection:
        return [row_to_dict(row) for row in connection.execute("SELECT * FROM flags ORDER BY updated_at DESC, reference DESC").fetchall()]


@app.get("/api/flags/{flag_id}")
def read_flag(flag_id: str, x_role: str = Header(default="analyst", alias="X-Role")) -> dict[str, object]:
    require_role(x_role, "analyst")
    with database() as connection:
        return row_to_dict(get_flag(connection, flag_id))


@app.get("/api/flags/{flag_id}/audit")
def read_flag_audit(flag_id: str, x_role: str = Header(default="analyst", alias="X-Role")) -> list[dict[str, object]]:
    require_role(x_role, "analyst")
    with database() as connection:
        get_flag(connection, flag_id)
        return audit_rows(connection, flag_id)


@app.get("/api/audit")
def read_global_audit(x_role: str = Header(default="analyst", alias="X-Role")) -> list[dict[str, object]]:
    require_role(x_role, "analyst")
    with database() as connection:
        return audit_rows(connection)


@app.post("/api/flags", status_code=201)
def create_flag(
    payload: FlagCreate,
    x_actor: str = Header(default="Demo analyst", alias="X-Actor"),
    x_role: str = Header(default="analyst", alias="X-Role"),
) -> dict[str, object]:
    require_role(x_role, "analyst")
    now = utc_now()
    flag_id = str(uuid.uuid4())
    with database() as connection:
        count = connection.execute("SELECT COUNT(*) FROM flags WHERE reference LIKE 'NGP-%'").fetchone()[0]
        reference = f"NGP-{datetime.now(timezone.utc).year}-{count + 1:05d}"
        connection.execute(
            """INSERT INTO flags
               (id, reference, zone_name, address, signal_label, latitude, longitude, area_hectares,
                signal_index, epoch_t0, epoch_t1, evidence_summary, status, priority, assignee, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (flag_id,reference,payload.zone_name.strip(),payload.address.strip(),payload.signal_label,payload.latitude,payload.longitude,payload.area_hectares,payload.signal_index,payload.epoch_t0.isoformat(),payload.epoch_t1.isoformat(),payload.evidence_summary.strip(),"new","normal",None,now,now),
        )
        flag = get_flag(connection, flag_id)
        add_audit_event(connection, flag, "FLAG_CREATED", x_actor[:120], "Flag created and entered analyst review", actor_role=x_role)
        return row_to_dict(flag)


@app.patch("/api/flags/{flag_id}")
def update_flag(
    flag_id: str,
    payload: FlagUpdate,
    x_actor: str = Header(default="Demo analyst", alias="X-Actor"),
    x_role: str = Header(default="analyst", alias="X-Role"),
) -> dict[str, object]:
    require_role(x_role, "analyst")
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=422, detail="Provide at least one field to update.")
    with database() as connection:
        current = get_flag(connection, flag_id)
        now = utc_now()
        for field, raw_value in changes.items():
            value = raw_value.strip() or None if field == "assignee" and isinstance(raw_value, str) else raw_value
            previous = current[field]
            if previous == value:
                continue
            summary = f"Status changed to {str(value).replace('_', ' ')}" if field == "status" else f"Assigned to {value or 'Unassigned'}" if field == "assignee" else f"Priority changed to {value}"
            connection.execute(f"UPDATE flags SET {field} = ?, updated_at = ? WHERE id = ?", (value, now, flag_id))
            current = get_flag(connection, flag_id)
            add_audit_event(connection, current, "STATUS_CHANGED" if field == "status" else "ASSIGNMENT_CHANGED" if field == "assignee" else "PRIORITY_CHANGED", x_actor[:120], summary, actor_role=x_role, from_value=str(previous) if previous is not None else None, to_value=str(value) if value is not None else None, created_at=now)
        return row_to_dict(get_flag(connection, flag_id))


@app.post("/api/flags/{flag_id}/notes", status_code=201)
def add_note(
    flag_id: str,
    payload: NoteCreate,
    x_actor: str = Header(default="Demo analyst", alias="X-Actor"),
    x_role: str = Header(default="analyst", alias="X-Role"),
) -> dict[str, object]:
    if x_role not in {"analyst", "authority"}:
        raise HTTPException(status_code=403, detail="Unknown portal role.")
    with database() as connection:
        flag = get_flag(connection, flag_id)
        note_text = payload.note.strip()
        if not note_text:
            raise HTTPException(status_code=422, detail="A note cannot be blank.")
        if x_role == "authority":
            require_authority_case(flag)
        event_id = add_audit_event(connection, flag, "NOTE_ADDED", x_actor[:120], "Review note added", actor_role=x_role, note=note_text)
        return row_to_dict(connection.execute("SELECT * FROM audit_events WHERE id = ?", (event_id,)).fetchone())


@app.get("/api/authority/flags")
def authority_flags(x_role: str = Header(default="analyst", alias="X-Role")) -> list[dict[str, object]]:
    require_role(x_role, "authority")
    with database() as connection:
        rows = connection.execute(
            """SELECT * FROM flags
               WHERE status IN ('authority_review', 'field_visit', 'action_taken', 'not_illegal')
               ORDER BY CASE WHEN status IN ('authority_review', 'field_visit') THEN 0 ELSE 1 END,
                        updated_at DESC"""
        ).fetchall()
        return [row_to_dict(row) for row in rows]


@app.get("/api/authority/flags/{flag_id}/audit")
def authority_flag_audit(flag_id: str, x_role: str = Header(default="analyst", alias="X-Role")) -> list[dict[str, object]]:
    require_role(x_role, "authority")
    with database() as connection:
        flag = get_flag(connection, flag_id)
        require_authority_case(flag)
        return audit_rows(connection, flag_id)


@app.post("/api/authority/flags/{flag_id}/decision")
def authority_decision(
    flag_id: str,
    payload: AuthorityDecision,
    x_actor: str = Header(default="Demo authority reviewer", alias="X-Actor"),
    x_role: str = Header(default="analyst", alias="X-Role"),
) -> dict[str, object]:
    require_role(x_role, "authority")
    comment = payload.comment.strip()
    if len(comment) < 3:
        raise HTTPException(status_code=422, detail="A decision comment of at least 3 characters is required.")
    with database() as connection:
        flag = get_flag(connection, flag_id)
        require_authority_case(flag)
        if flag["status"] in {"action_taken", "not_illegal"}:
            raise HTTPException(status_code=409, detail="This flag already has an authority decision.")
        previous = str(flag["status"])
        now = utc_now()
        summary = "Authority action recorded" if payload.outcome == "action_taken" else "Flag marked not illegal"
        connection.execute("UPDATE flags SET status = ?, updated_at = ? WHERE id = ?", (payload.outcome, now, flag_id))
        updated = get_flag(connection, flag_id)
        add_audit_event(
            connection,
            updated,
            "AUTHORITY_ACTION_TAKEN" if payload.outcome == "action_taken" else "AUTHORITY_MARKED_NOT_ILLEGAL",
            x_actor[:120],
            summary,
            actor_role=x_role,
            note=comment,
            from_value=previous,
            to_value=payload.outcome,
            created_at=now,
        )
        return row_to_dict(updated)


def monthly_metrics_payload(months: int) -> dict[str, object]:
    current = datetime.now(timezone.utc).date().replace(day=1)
    month_keys: list[str] = []
    for offset in reversed(range(months)):
        absolute = current.year * 12 + current.month - 1 - offset
        year, month_index = divmod(absolute, 12)
        month_keys.append(f"{year:04d}-{month_index + 1:02d}")
    earliest = f"{month_keys[0]}-01T00:00:00"
    with database() as connection:
        corporations = [row["corporation_name"] for row in connection.execute("SELECT DISTINCT corporation_name FROM flags ORDER BY corporation_name")]
        aggregates = connection.execute(
            """SELECT f.corporation_name, substr(e.created_at, 1, 7) AS month,
                      SUM(CASE WHEN e.action = 'AUTHORITY_ACTION_TAKEN' THEN 1 ELSE 0 END) AS action_taken,
                      SUM(CASE WHEN e.action = 'AUTHORITY_MARKED_NOT_ILLEGAL' THEN 1 ELSE 0 END) AS not_illegal
               FROM audit_events e JOIN flags f ON f.id = e.flag_id
               WHERE e.action IN ('AUTHORITY_ACTION_TAKEN', 'AUTHORITY_MARKED_NOT_ILLEGAL') AND e.created_at >= ?
               GROUP BY f.corporation_name, substr(e.created_at, 1, 7)""",
            (earliest,),
        ).fetchall()
    by_corporation: dict[str, dict[str, sqlite3.Row]] = {}
    for row in aggregates:
        by_corporation.setdefault(row["corporation_name"], {})[row["month"]] = row
    return {
        "months": month_keys,
        "corporations": [
            {
                "corporation_name": corporation,
                "items": [
                    {
                        "month": month,
                        "action_taken": int(by_corporation.get(corporation, {}).get(month)["action_taken"] or 0) if month in by_corporation.get(corporation, {}) else 0,
                        "not_illegal": int(by_corporation.get(corporation, {}).get(month)["not_illegal"] or 0) if month in by_corporation.get(corporation, {}) else 0,
                    }
                    for month in month_keys
                ],
            }
            for corporation in corporations
        ],
    }


@app.get("/api/authority/metrics/monthly")
def authority_monthly_metrics(
    months: int = Query(default=12, ge=1, le=36),
    x_role: str = Header(default="analyst", alias="X-Role"),
) -> dict[str, object]:
    require_role(x_role, "authority")
    return monthly_metrics_payload(months)


@app.get("/api/corporation/metrics/monthly")
def corporation_monthly_metrics(
    months: int = Query(default=12, ge=1, le=36),
    x_role: str = Header(default="analyst", alias="X-Role"),
) -> dict[str, object]:
    require_role(x_role, "analyst")
    return monthly_metrics_payload(months)