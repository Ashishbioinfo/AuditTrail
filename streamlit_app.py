from __future__ import annotations

import csv
import io
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

import pandas as pd
import streamlit as st


DATABASE_PATH = Path(
    os.environ.get(
        "ABHILEKH_DB_PATH",
        Path(__file__).resolve().parent / "backend" / "data" / "flags.db",
    )
)
ANALYSTS = ["A. Kulkarni", "R. Mehta", "S. Deshmukh"]
AUTHORITIES = ["P. Rao", "A. Wankhede", "Municipal review desk"]
STATUS_LABELS = {
    "new": "New",
    "triage": "Analyst review",
    "assigned": "Assigned",
    "authority_review": "Authority review",
    "field_visit": "Field visit",
    "confirmed": "Confirmed",
    "not_confirmed": "Not confirmed",
    "closed": "Closed",
    "action_taken": "Action taken",
    "not_illegal": "Not illegal",
}
AUTHORITY_STATUSES = ("authority_review", "field_visit", "action_taken", "not_illegal")
DECIDED_STATUSES = ("confirmed", "not_confirmed", "closed", "action_taken", "not_illegal")


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
                source_id TEXT, source_project TEXT,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT, flag_id TEXT NOT NULL REFERENCES flags(id),
                flag_reference TEXT NOT NULL, action TEXT NOT NULL, actor TEXT NOT NULL,
                actor_role TEXT NOT NULL DEFAULT 'system', summary TEXT NOT NULL, note TEXT,
                from_value TEXT, to_value TEXT, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS authority_attachments (
                id TEXT PRIMARY KEY, flag_id TEXT NOT NULL REFERENCES flags(id),
                filename TEXT NOT NULL, media_type TEXT NOT NULL, content BLOB NOT NULL,
                uploaded_by TEXT NOT NULL, uploaded_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_flags_status ON flags(status);
            CREATE INDEX IF NOT EXISTS idx_audit_flag_created ON audit_events(flag_id, created_at DESC);
            CREATE TRIGGER IF NOT EXISTS audit_events_no_update BEFORE UPDATE ON audit_events BEGIN
                SELECT RAISE(ABORT, 'Audit events are append-only'); END;
            CREATE TRIGGER IF NOT EXISTS audit_events_no_delete BEFORE DELETE ON audit_events BEGIN
                SELECT RAISE(ABORT, 'Audit events are append-only'); END;
            CREATE TRIGGER IF NOT EXISTS authority_attachments_no_update BEFORE UPDATE ON authority_attachments BEGIN
                SELECT RAISE(ABORT, 'Authority attachments are append-only'); END;
            CREATE TRIGGER IF NOT EXISTS authority_attachments_no_delete BEFORE DELETE ON authority_attachments BEGIN
                SELECT RAISE(ABORT, 'Authority attachments are append-only'); END;
            """
        )
        flag_columns = {row["name"] for row in connection.execute("PRAGMA table_info(flags)")}
        if "corporation_name" not in flag_columns:
            connection.execute(
                "ALTER TABLE flags ADD COLUMN corporation_name TEXT NOT NULL DEFAULT 'Nagpur Municipal Corporation'"
            )
        if "source_id" not in flag_columns:
            connection.execute("ALTER TABLE flags ADD COLUMN source_id TEXT")
        if "source_project" not in flag_columns:
            connection.execute("ALTER TABLE flags ADD COLUMN source_project TEXT")
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_flags_source_id ON flags(source_id) WHERE source_id IS NOT NULL"
        )
        audit_columns = {row["name"] for row in connection.execute("PRAGMA table_info(audit_events)")}
        if "actor_role" not in audit_columns:
            connection.execute(
                "ALTER TABLE audit_events ADD COLUMN actor_role TEXT NOT NULL DEFAULT 'analyst'"
            )
        seed_demo_flags(connection)


def seed_demo_flags(connection: sqlite3.Connection) -> None:
    if connection.execute("SELECT COUNT(*) FROM flags").fetchone()[0]:
        return
    today = datetime.now(timezone.utc).date()
    samples = [
        ("NGP-2026-00127", "Laxmi Nagar · Zone 1", "North of Ring Road, parcel sector 04", "Built-surface gain", 21.1215, 79.0645, 0.14, 78, 365, 12, "Illustrative spectral signal: built-surface index rose while vegetation index declined. Review cloud cover, alignment, and site history before routing.", "triage", "high", "R. Mehta", 1),
        ("NGP-2026-00126", "Dharampeth · Zone 2", "Near Civil Lines connector, block 11", "Land-clearing candidate", 21.1438, 79.0621, 0.08, 61, 340, 9, "Illustrative vegetation-loss signal across two scenes. Seasonal change and temporary site preparation remain possible explanations.", "new", "normal", None, 2),
        ("NGP-2026-00119", "Dhantoli · Zone 4", "South-east grid, ward parcel 7B", "Built-surface gain", 21.1405, 79.0838, 0.23, 84, 365, 28, "Illustrative change candidate routed for permit verification. This record is seeded demo data, not an observed violation.", "authority_review", "high", "Municipal review desk", 4),
        ("NGP-2026-00108", "Nehru Nagar · Zone 5", "Central residential grid, lane 2", "SAR-supported change", 21.1284, 79.1176, 0.11, 55, 180, 18, "Illustrative paired-scene signal awaiting a field visit. SAR change is a screening proxy and does not measure building height.", "field_visit", "normal", "S. Deshmukh", 7),
        ("NGP-2026-00098", "Mangalwari · Zone 10", "Market approach, sector 3A", "Land-clearing candidate", 21.1764, 79.0718, 0.05, 34, 365, 45, "Illustrative record closed as not confirmed in the demo workflow. This is not a real authority determination.", "not_confirmed", "low", "Municipal review desk", 12),
    ]
    for sample in samples:
        reference, zone, address, signal, latitude, longitude, area, index, t0_days, t1_days, evidence, status, priority, assignee, age_days = sample
        created_at = (datetime.now(timezone.utc) - timedelta(days=age_days)).isoformat(timespec="seconds").replace("+00:00", "Z")
        flag_id = str(uuid.uuid4())
        connection.execute(
            """INSERT INTO flags
               (id, reference, zone_name, address, signal_label, latitude, longitude, area_hectares,
                signal_index, epoch_t0, epoch_t1, evidence_summary, status, priority, assignee, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (flag_id, reference, zone, address, signal, latitude, longitude, area, index,
             (today - timedelta(days=t0_days)).isoformat(), (today - timedelta(days=t1_days)).isoformat(),
             evidence, status, priority, assignee, created_at, created_at),
        )
        flag = connection.execute("SELECT * FROM flags WHERE id = ?", (flag_id,)).fetchone()
        add_audit_event(connection, flag, "FLAG_CREATED", "Screening demo", "Flag created from illustrative screening data", created_at=created_at)
        if status != "new":
            add_audit_event(
                connection, flag, "STATUS_CHANGED", assignee or "Demo analyst",
                f"Seeded demo status: {status.replace('_', ' ')}", from_value="new", to_value=status,
                created_at=created_at,
            )


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
) -> None:
    connection.execute(
        """INSERT INTO audit_events
           (flag_id, flag_reference, action, actor, actor_role, summary, note, from_value, to_value, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (flag["id"], flag["reference"], action, actor[:120], actor_role, summary, note,
         from_value, to_value, created_at or utc_now()),
    )


def list_flags(authority: bool = False) -> list[dict[str, object]]:
    with database() as connection:
        if authority:
            rows = connection.execute(
                """SELECT * FROM flags WHERE status IN (?, ?, ?, ?)
                   ORDER BY CASE WHEN status IN (?, ?) THEN 0 ELSE 1 END, updated_at DESC""",
                (*AUTHORITY_STATUSES, "authority_review", "field_visit"),
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT * FROM flags ORDER BY updated_at DESC, reference DESC"
            ).fetchall()
        return [dict(row) for row in rows]


def list_audit(flag_id: str | None = None) -> list[dict[str, object]]:
    with database() as connection:
        if flag_id:
            rows = connection.execute(
                "SELECT * FROM audit_events WHERE flag_id = ? ORDER BY created_at DESC, id DESC",
                (flag_id,),
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT * FROM audit_events ORDER BY created_at DESC, id DESC LIMIT 500"
            ).fetchall()
        return [dict(row) for row in rows]


def import_detector_csv(contents: bytes, actor: str) -> tuple[int, int, list[str]]:
    try:
        text = contents.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError("The detector export must be a UTF-8 CSV file.") from error
    reader = csv.DictReader(io.StringIO(text))
    required = {
        "source_id", "zone_name", "signal_label", "latitude", "longitude",
        "area_hectares", "epoch_t0", "epoch_t1", "evidence_summary",
    }
    if not reader.fieldnames or not required.issubset(reader.fieldnames):
        missing = ", ".join(sorted(required - set(reader.fieldnames or [])))
        raise ValueError(f"This file is not a Construction Watch export. Missing columns: {missing}.")

    imported = 0
    duplicates = 0
    errors: list[str] = []
    with database() as connection:
        reference_number = connection.execute(
            "SELECT COUNT(*) FROM flags WHERE reference LIKE 'NGP-%'"
        ).fetchone()[0]
        seen: set[str] = set()
        for row_number, row in enumerate(reader, start=2):
            source_id = (row.get("source_id") or "").strip()
            if not source_id:
                errors.append(f"Row {row_number}: source_id is blank.")
                continue
            if source_id in seen or connection.execute(
                "SELECT 1 FROM flags WHERE source_id = ?", (source_id,)
            ).fetchone():
                duplicates += 1
                seen.add(source_id)
                continue
            seen.add(source_id)
            try:
                zone_name = (row.get("zone_name") or "").strip()
                signal_label = (row.get("signal_label") or "").strip()
                latitude = float(row.get("latitude") or "")
                longitude = float(row.get("longitude") or "")
                area_hectares = float(row.get("area_hectares") or "")
                epoch_t0 = date.fromisoformat((row.get("epoch_t0") or "")[:10])
                epoch_t1 = date.fromisoformat((row.get("epoch_t1") or "")[:10])
                evidence = (row.get("evidence_summary") or "").strip()
                signal_index_text = (row.get("signal_index") or "").strip()
                signal_index = int(float(signal_index_text)) if signal_index_text else 0
                if not zone_name or not signal_label or len(evidence) < 5:
                    raise ValueError("zone, signal, and evidence summary are required")
                if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
                    raise ValueError("coordinates are outside valid latitude/longitude ranges")
                if area_hectares <= 0 or not 0 <= signal_index <= 100:
                    raise ValueError("area must be positive and signal index must be between 0 and 100")
                if epoch_t0 >= epoch_t1:
                    raise ValueError("epoch_t0 must be earlier than epoch_t1")
            except (TypeError, ValueError) as error:
                errors.append(f"Row {row_number}: {error}.")
                continue

            now = utc_now()
            flag_id = str(uuid.uuid4())
            reference_number += 1
            reference = f"NGP-{datetime.now(timezone.utc).year}-{reference_number:05d}"
            source_project = (row.get("source_project") or "Construction Watch").strip()
            address = (row.get("address") or "Satellite-screened candidate; address not provided").strip()
            connection.execute(
                """INSERT INTO flags
                   (id, reference, zone_name, address, signal_label, latitude, longitude, area_hectares,
                    signal_index, epoch_t0, epoch_t1, evidence_summary, status, priority, assignee,
                    source_id, source_project, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new', 'normal', NULL, ?, ?, ?, ?)""",
                (flag_id, reference, zone_name, address, signal_label, latitude, longitude,
                 area_hectares, signal_index, epoch_t0.isoformat(), epoch_t1.isoformat(),
                 evidence[:2000], source_id, source_project, now, now),
            )
            flag = connection.execute("SELECT * FROM flags WHERE id = ?", (flag_id,)).fetchone()
            add_audit_event(
                connection, flag, "FLAG_IMPORTED", actor,
                f"Screening anomaly imported from {source_project}", actor_role="analyst",
                note=f"Source record: {source_id}", created_at=now,
            )
            imported += 1
    return imported, duplicates, errors


def update_flag(flag_id: str, changes: dict[str, object], actor: str) -> None:
    allowed = {"status", "priority", "assignee"}
    if not changes or not set(changes).issubset(allowed):
        raise ValueError("Choose a valid case update.")
    with database() as connection:
        current = connection.execute("SELECT * FROM flags WHERE id = ?", (flag_id,)).fetchone()
        if current is None:
            raise ValueError("Flag not found.")
        now = utc_now()
        for field, raw_value in changes.items():
            value = (str(raw_value).strip() or None) if field == "assignee" else raw_value
            previous = current[field]
            if previous == value:
                continue
            action = {"status": "STATUS_CHANGED", "assignee": "ASSIGNMENT_CHANGED", "priority": "PRIORITY_CHANGED"}[field]
            summary = (
                f"Status changed to {str(value).replace('_', ' ')}" if field == "status"
                else f"Assigned to {value or 'Unassigned'}" if field == "assignee"
                else f"Priority changed to {value}"
            )
            connection.execute(f"UPDATE flags SET {field} = ?, updated_at = ? WHERE id = ?", (value, now, flag_id))
            current = connection.execute("SELECT * FROM flags WHERE id = ?", (flag_id,)).fetchone()
            add_audit_event(
                connection, current, action, actor, summary, actor_role="analyst",
                from_value=str(previous) if previous is not None else None,
                to_value=str(value) if value is not None else None, created_at=now,
            )


def create_flag(values: dict[str, object], actor: str) -> str:
    if values["epoch_t0"] >= values["epoch_t1"]:
        raise ValueError("Epoch T0 must be earlier than Epoch T1.")
    if not -90 <= float(values["latitude"]) <= 90 or not -180 <= float(values["longitude"]) <= 180:
        raise ValueError("Enter valid latitude and longitude values.")
    if float(values["area_hectares"]) <= 0 or not 0 <= int(values["signal_index"]) <= 100:
        raise ValueError("Area must be positive and signal index must be between 0 and 100.")
    now = utc_now()
    flag_id = str(uuid.uuid4())
    with database() as connection:
        count = connection.execute("SELECT COUNT(*) FROM flags WHERE reference LIKE 'NGP-%'").fetchone()[0]
        reference = f"NGP-{datetime.now(timezone.utc).year}-{count + 1:05d}"
        connection.execute(
            """INSERT INTO flags
               (id, reference, zone_name, address, signal_label, latitude, longitude, area_hectares,
                signal_index, epoch_t0, epoch_t1, evidence_summary, status, priority, assignee, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new', 'normal', NULL, ?, ?)""",
            (flag_id, reference, str(values["zone_name"]).strip(), str(values["address"]).strip(),
             str(values["signal_label"]), float(values["latitude"]), float(values["longitude"]),
             float(values["area_hectares"]), int(values["signal_index"]), str(values["epoch_t0"]),
             str(values["epoch_t1"]), str(values["evidence_summary"]).strip(), now, now),
        )
        flag = connection.execute("SELECT * FROM flags WHERE id = ?", (flag_id,)).fetchone()
        add_audit_event(connection, flag, "FLAG_CREATED", actor, "Flag created and entered analyst review", actor_role="analyst")
    return flag_id


def add_note(flag_id: str, note: str, actor: str, role: str) -> None:
    note = note.strip()
    if not note:
        raise ValueError("A note cannot be blank.")
    with database() as connection:
        flag = connection.execute("SELECT * FROM flags WHERE id = ?", (flag_id,)).fetchone()
        if flag is None:
            raise ValueError("Flag not found.")
        if role == "authority" and flag["status"] not in AUTHORITY_STATUSES:
            raise ValueError("This flag has not been referred to the authority portal.")
        add_audit_event(connection, flag, "NOTE_ADDED", actor, "Review note added", actor_role=role, note=note[:2000])


def list_attachments(flag_id: str) -> list[dict[str, object]]:
    with database() as connection:
        rows = connection.execute(
            """SELECT id, filename, media_type, length(content) AS size_bytes, uploaded_by, uploaded_at
               FROM authority_attachments WHERE flag_id = ? ORDER BY uploaded_at DESC""",
            (flag_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def save_authority_attachment(
    flag_id: str,
    filename: str,
    media_type: str,
    content: bytes,
    actor: str,
) -> None:
    if not content:
        raise ValueError("Choose a non-empty file to attach.")
    if len(content) > 15 * 1024 * 1024:
        raise ValueError("Attachments must be 15 MB or smaller.")
    safe_filename = filename.replace("\\", "/").split("/")[-1].strip()
    if not safe_filename:
        raise ValueError("The attachment must have a filename.")
    with database() as connection:
        flag = connection.execute("SELECT * FROM flags WHERE id = ?", (flag_id,)).fetchone()
        if flag is None or flag["status"] not in AUTHORITY_STATUSES:
            raise ValueError("Attachments can only be added to referred authority cases.")
        attachment_id = str(uuid.uuid4())
        uploaded_at = utc_now()
        connection.execute(
            """INSERT INTO authority_attachments
               (id, flag_id, filename, media_type, content, uploaded_by, uploaded_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (attachment_id, flag_id, safe_filename, media_type or "application/octet-stream",
             sqlite3.Binary(content), actor[:120], uploaded_at),
        )
        add_audit_event(
            connection, flag, "ATTACHMENT_ADDED", actor, "Authority evidence attached",
            actor_role="authority", note=safe_filename, created_at=uploaded_at,
        )


def read_attachment(flag_id: str, attachment_id: str) -> tuple[dict[str, object], bytes] | None:
    with database() as connection:
        row = connection.execute(
            """SELECT id, filename, media_type, content, uploaded_by, uploaded_at
               FROM authority_attachments WHERE flag_id = ? AND id = ?""",
            (flag_id, attachment_id),
        ).fetchone()
        if row is None:
            return None
        metadata = {key: row[key] for key in ("id", "filename", "media_type", "uploaded_by", "uploaded_at")}
        return metadata, bytes(row["content"])


def record_decision(flag_id: str, outcome: str, comment: str, actor: str) -> None:
    comment = comment.strip()
    if outcome not in ("action_taken", "not_illegal") or len(comment) < 3:
        raise ValueError("Choose an outcome and enter a comment of at least 3 characters.")
    with database() as connection:
        flag = connection.execute("SELECT * FROM flags WHERE id = ?", (flag_id,)).fetchone()
        if flag is None or flag["status"] not in AUTHORITY_STATUSES:
            raise ValueError("This flag has not been referred to the authority portal.")
        if flag["status"] in DECIDED_STATUSES:
            raise ValueError("This flag already has an authority decision.")
        previous = str(flag["status"])
        now = utc_now()
        connection.execute("UPDATE flags SET status = ?, updated_at = ? WHERE id = ?", (outcome, now, flag_id))
        updated = connection.execute("SELECT * FROM flags WHERE id = ?", (flag_id,)).fetchone()
        add_audit_event(
            connection, updated,
            "AUTHORITY_ACTION_TAKEN" if outcome == "action_taken" else "AUTHORITY_MARKED_NOT_ILLEGAL",
            actor, "Authority action recorded" if outcome == "action_taken" else "Flag marked not illegal",
            actor_role="authority", note=comment[:2000], from_value=previous, to_value=outcome, created_at=now,
        )


def monthly_report(months: int = 12) -> tuple[pd.DataFrame, int, int]:
    current = datetime.now(timezone.utc).date().replace(day=1)
    month_dates = []
    for offset in reversed(range(months)):
        absolute = current.year * 12 + current.month - 1 - offset
        year, month_index = divmod(absolute, 12)
        month_dates.append(date(year, month_index + 1, 1))
    month_keys = [month.strftime("%Y-%m") for month in month_dates]
    with database() as connection:
        rows = connection.execute(
            """SELECT substr(created_at, 1, 7) AS month,
                      SUM(CASE WHEN action = 'AUTHORITY_ACTION_TAKEN' THEN 1 ELSE 0 END) AS action_taken,
                      SUM(CASE WHEN action = 'AUTHORITY_MARKED_NOT_ILLEGAL' THEN 1 ELSE 0 END) AS not_illegal
               FROM audit_events
               WHERE action IN ('AUTHORITY_ACTION_TAKEN', 'AUTHORITY_MARKED_NOT_ILLEGAL')
                 AND created_at >= ?
               GROUP BY substr(created_at, 1, 7)""",
            (f"{month_keys[0]}-01T00:00:00",),
        ).fetchall()
    totals = {row["month"]: row for row in rows}
    report = pd.DataFrame(
        [
            {
                "Month": month.strftime("%b %Y"),
                "Action taken": int(totals.get(key)["action_taken"] or 0) if key in totals else 0,
                "Not illegal": int(totals.get(key)["not_illegal"] or 0) if key in totals else 0,
            }
            for month, key in zip(month_dates, month_keys)
        ]
    )
    return report, int(report["Action taken"].sum()), int(report["Not illegal"].sum())


def format_date(value: str) -> str:
    return date.fromisoformat(value[:10]).strftime("%d %b %Y")


def get_flag(flag_id: str) -> dict[str, object] | None:
    with database() as connection:
        row = connection.execute("SELECT * FROM flags WHERE id = ?", (flag_id,)).fetchone()
        return dict(row) if row else None


def show_monthly_report() -> None:
    st.subheader("Monthly authority actions")
    st.caption("Authority outcomes recorded in the append-only audit history.")
    report, action_total, clear_total = monthly_report()
    first, second, third = st.columns(3)
    first.metric("Action taken", action_total)
    second.metric("Not illegal", clear_total)
    third.metric("Total decisions", action_total + clear_total)
    chart_data = report.set_index("Month")
    st.bar_chart(chart_data, color=["#bd6044", "#547d66"], stack=True)
    st.dataframe(report, hide_index=True, width="stretch")


def show_authority_attachments(flag: dict[str, object], actor: str) -> None:
    flag_id = str(flag["id"])
    st.markdown("**Authority evidence files**")
    with st.form(f"authority_upload_{flag_id}", clear_on_submit=True):
        uploaded = st.file_uploader(
            "Attach permit, inspection, or decision evidence",
            type=["pdf", "png", "jpg", "jpeg", "tif", "tiff", "doc", "docx", "xlsx", "csv", "txt"],
            help="Maximum 15 MB per file. Files are retained in the case database and cannot be edited or deleted.",
        )
        submit_upload = st.form_submit_button("Attach to authority case", type="primary")
    if submit_upload:
        if uploaded is None:
            st.error("Choose a file before attaching it.")
        else:
            try:
                save_authority_attachment(
                    flag_id, uploaded.name, uploaded.type, uploaded.getvalue(), actor
                )
                st.success("Evidence attached and added to case history.")
                st.rerun()
            except ValueError as error:
                st.error(str(error))

    attachments = list_attachments(flag_id)
    if not attachments:
        st.caption("No authority files attached to this case.")
        return
    for attachment in attachments:
        stored = read_attachment(flag_id, str(attachment["id"]))
        if stored is None:
            continue
        metadata, content = stored
        download, details = st.columns([1.3, 1])
        download.download_button(
            f"Download {metadata['filename']}",
            data=content,
            file_name=str(metadata["filename"]),
            mime=str(metadata["media_type"]),
            key=f"download_{metadata['id']}",
            width="stretch",
        )
        details.caption(f"Added by {metadata['uploaded_by']} · {str(metadata['uploaded_at'])[:16]} UTC · {len(content) / 1024:.0f} KB")


def show_case_history(flag_id: str) -> None:
    st.markdown("**Append-only case history**")
    events = list_audit(flag_id)
    if events:
        for event in events:
            with st.container(border=True):
                st.markdown(f"**{event['summary']}**")
                created_at = datetime.fromisoformat(
                    str(event["created_at"]).replace("Z", "+00:00")
                ).strftime("%d %b %Y · %H:%M UTC")
                st.caption(f"{event['actor']} · {event['actor_role']} · {created_at}")
                if event["note"]:
                    st.write(str(event["note"]))
    else:
        st.caption("No activity recorded.")


def show_flag_details(
    flag: dict[str, object], actor: str, role: str, *, include_history: bool = True
) -> None:
    st.divider()
    st.subheader(f"{flag['reference']} · {flag['signal_label']}")
    st.caption(
        f"{STATUS_LABELS.get(str(flag['status']), str(flag['status']))}  ·  "
        f"{str(flag['priority']).title()} priority  ·  {format_date(str(flag['created_at']))}"
    )
    st.write(f"**{flag['zone_name']}** · {flag['address']}")
    st.caption(f"Created {format_date(str(flag['created_at']))} · {float(flag['area_hectares']):.2f} ha · Priority: {flag['priority']}")

    left, right = st.columns([1.5, 1])
    with left:
        st.map(pd.DataFrame([{"latitude": flag["latitude"], "longitude": flag["longitude"]}]), latitude="latitude", longitude="longitude", zoom=14)
        st.caption(f"{float(flag['latitude']):.5f}, {float(flag['longitude']):.5f} · OpenStreetMap")
    with right:
        st.markdown("**Location evidence**")
        if flag.get("source_id"):
            st.write("Signal score: **Not provided by source detector**")
            st.caption(f"Imported from {flag.get('source_project') or 'external detector'} · source ID {flag['source_id']}")
        else:
            st.write(f"Signal index: **{flag['signal_index']} / 100**")
        st.write(f"Scene period: {format_date(str(flag['epoch_t0']))} → {format_date(str(flag['epoch_t1']))}")
        st.write(str(flag["evidence_summary"]))
        st.info("Screening output is an investigative lead, not a legal determination. Validate source imagery and permit records.")

    if role == "analyst":
        st.markdown("**Analyst actions**")
        action_rows = [
            st.columns(2),
            st.columns(2),
        ]
        actions = [
            ("Send to authority", "authority_review"),
            ("Request field visit", "field_visit"),
            ("Confirm signal", "confirmed"),
            ("Mark not confirmed", "not_confirmed"),
        ]
        for column, (label, new_status) in zip(
            [column for row in action_rows for column in row], actions
        ):
            if column.button(label, key=f"{flag['id']}_{new_status}", width="stretch"):
                update_flag(str(flag["id"]), {"status": new_status}, actor)
                st.rerun()
        with st.form(f"assignment_{flag['id']}"):
            reviewer_options = ["Unassigned", *ANALYSTS, *AUTHORITIES]
            current_assignee = str(flag["assignee"] or "Unassigned")
            if current_assignee not in reviewer_options:
                reviewer_options.append(current_assignee)
            selected_reviewer = st.selectbox("Assigned reviewer", reviewer_options, index=reviewer_options.index(current_assignee))
            selected_priority = st.selectbox("Priority", ["low", "normal", "high"], index=["low", "normal", "high"].index(str(flag["priority"])))
            save_assignment = st.form_submit_button("Save assignment and priority")
        if save_assignment:
            assigned_to = None if selected_reviewer == "Unassigned" else selected_reviewer
            changes: dict[str, object] = {"assignee": assigned_to, "priority": selected_priority}
            if assigned_to != flag["assignee"]:
                changes["status"] = "assigned" if assigned_to else "triage"
            update_flag(str(flag["id"]), changes, actor)
            st.success("Case assignment updated.")
            st.rerun()
        with st.form(f"note_{flag['id']}", clear_on_submit=True):
            note = st.text_area("Add review note", max_chars=2000, placeholder="Record a review observation.")
            add_note_button = st.form_submit_button("Add note")
        if add_note_button:
            add_note(str(flag["id"]), note, actor, role)
            st.success("Note added to case history.")
            st.rerun()
    elif flag["status"] in ("authority_review", "field_visit"):
        st.markdown("**Authority determination**")
        with st.form(f"decision_{flag['id']}"):
            outcome = st.radio("Outcome", ["action_taken", "not_illegal"], format_func=lambda value: "Action taken" if value == "action_taken" else "Not illegal", horizontal=True)
            comment = st.text_area("Review comment (required)", max_chars=2000)
            submit_decision = st.form_submit_button("Record authority decision")
        if submit_decision:
            record_decision(str(flag["id"]), outcome, comment, actor)
            st.success("Decision and comment recorded in the case history.")
            st.rerun()
    else:
        st.success(f"Final outcome: {STATUS_LABELS.get(str(flag['status']), str(flag['status']))}")
        if role == "authority":
            with st.form(f"authority_note_{flag['id']}", clear_on_submit=True):
                note = st.text_area("Add case note", max_chars=2000)
                add_note_button = st.form_submit_button("Add note")
            if add_note_button:
                add_note(str(flag["id"]), note, actor, role)
                st.success("Note added to case history.")
                st.rerun()

    if role == "authority":
        show_authority_attachments(flag, actor)
    if include_history:
        show_case_history(str(flag["id"]))


def show_create_flag(actor: str) -> None:
    with st.expander("Create a flag", expanded=st.session_state.get("show_create", False)):
        with st.form("create_flag", clear_on_submit=True):
            zone = st.text_input("Zone", placeholder="e.g. Laxmi Nagar, Zone 1")
            signal = st.selectbox("Signal type", ["Built-surface gain", "Land-clearing candidate", "SAR-supported change", "Manual field observation"])
            address = st.text_input("Address or landmark")
            first, second = st.columns(2)
            latitude = first.number_input("Latitude", min_value=-90.0, max_value=90.0, value=21.1215, format="%.5f")
            longitude = second.number_input("Longitude", min_value=-180.0, max_value=180.0, value=79.0645, format="%.5f")
            area, index = st.columns(2)
            area_hectares = area.number_input("Approx. area (ha)", min_value=0.01, value=0.03, step=0.01)
            signal_index = index.slider("Signal index", min_value=0, max_value=100, value=62)
            epoch_t0 = st.date_input("Epoch T0", value=date.today() - timedelta(days=365))
            epoch_t1 = st.date_input("Epoch T1", value=date.today() - timedelta(days=12))
            evidence = st.text_area("Evidence summary", value="Candidate generated for analyst review. Verify image quality, mapped footprint, and permit records.", max_chars=2000)
            submitted = st.form_submit_button("Add to review queue", type="primary")
        if submitted:
            if not zone.strip() or not address.strip() or len(evidence.strip()) < 5:
                st.error("Enter a zone, address, and evidence summary.")
            else:
                try:
                    new_id = create_flag(
                        {"zone_name": zone, "address": address, "signal_label": signal,
                         "latitude": latitude, "longitude": longitude, "area_hectares": area_hectares,
                         "signal_index": signal_index, "epoch_t0": epoch_t0.isoformat(),
                         "epoch_t1": epoch_t1.isoformat(), "evidence_summary": evidence},
                        actor,
                    )
                    st.session_state["analyst_selected_flag"] = new_id
                    st.session_state["show_create"] = False
                    st.success("Flag added to the review queue.")
                    st.rerun()
                except ValueError as error:
                    st.error(str(error))


def show_detector_import(actor: str) -> None:
    with st.expander("Import anomalies from Construction Watch"):
        st.caption("In Construction Watch, export the selected candidate layer, then upload that CSV here. Re-imports are deduplicated by source ID.")
        uploaded = st.file_uploader("Detection export CSV", type=["csv"], key="detector_csv_upload")
        if st.button("Import detections", disabled=uploaded is None, key="import_detector_csv", type="primary"):
            try:
                imported, duplicates, errors = import_detector_csv(uploaded.getvalue(), actor)
                st.success(f"Imported {imported} flag(s); skipped {duplicates} duplicate(s).")
                if errors:
                    st.warning(f"{len(errors)} row(s) could not be imported.")
                    for error in errors[:10]:
                        st.caption(error)
                if imported:
                    st.rerun()
            except ValueError as error:
                st.error(str(error))


def main() -> None:
    st.set_page_config(page_title="AbhiLekh · Flag Review", page_icon="🧭", layout="wide")
    st.markdown(
        """<style>
        @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@500;600;700;800&display=swap');
        :root { --ink: #202b25; --muted: #727d74; --line: #e1e6df; --paper: #f3f5f0; --surface: #fffefa; --green: #284c3d; --green-dark: #1d3b2f; --clay: #b45238; }
        html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; color: var(--ink); letter-spacing: 0; }
        .stApp { background: radial-gradient(ellipse at 82% 0%, #e9eee5 0, var(--paper) 46rem); }
        .block-container { max-width: 1780px; padding: 1.35rem 1.1rem 2rem; }
        h1, h2, h3 { font-family: 'Manrope', sans-serif; letter-spacing: 0; }
        h1 { font-size: 1.9rem; font-weight: 800; color: #22382b; }
        h2, h3 { color: #304836; }
        section[data-testid="stSidebar"] { min-width: 255px !important; max-width: 255px !important; background: #eaf0e8; border-right: 1px solid #dce4db; }
        [data-testid="stMetric"] { background: var(--surface); border: 1px solid var(--line); border-top: 2px solid #a9694d; border-radius: 5px; padding: 14px 16px; box-shadow: 0 2px 8px rgba(27,53,35,.025); }
        [data-testid="stMetricLabel"] { color: var(--muted); font-size: .72rem; font-weight: 700; text-transform: uppercase; }
        [data-testid="stMetricValue"] { color: #2d4937; font-family: 'Manrope', sans-serif; font-weight: 800; }
        [data-testid="stVerticalBlockBorderWrapper"] { border-color: var(--line); border-radius: 6px; background: var(--surface); }
        div.stButton > button, div.stFormSubmitButton > button { min-height: 2.35rem; border-radius: 4px; font-size: .82rem; font-weight: 700; }
        div.stButton > button[kind="primary"], div.stFormSubmitButton > button[kind="primary"] { background: var(--green); border-color: var(--green); }
        div.stButton > button[kind="primary"]:hover, div.stFormSubmitButton > button[kind="primary"]:hover { background: var(--green-dark); border-color: var(--green-dark); }
        div[data-testid="stDataFrame"] { border: 1px solid var(--line); }
        .brand { font-family: 'Manrope', sans-serif; font-size: 1.35rem; font-weight: 800; color: var(--green); }
        .eyebrow { color: var(--muted); font-size: .69rem; font-weight: 700; letter-spacing: .08em; }
        .portal-header { display: flex; align-items: flex-end; justify-content: space-between; gap: 1rem; margin: .3rem 0 1rem; padding: 0 0 1rem; border-bottom: 1px solid var(--line); }
        .portal-header-note { padding: .45rem .65rem; border: 1px solid #e8dfcb; border-radius: 4px; color: #806c42; background: #faf6eb; font: 600 .68rem 'IBM Plex Mono', monospace; white-space: nowrap; }
        .queue-count { color: #7c887e; font-size: .72rem; }
        .stFileUploader { border-color: var(--line); }
        @media (max-width: 800px) { .block-container { padding-right: .75rem; padding-left: .75rem; } .portal-header { align-items: flex-start; flex-direction: column; } .portal-header-note { white-space: normal; } }
        </style>""",
        unsafe_allow_html=True,
    )
    initialize_database()

    with st.sidebar:
        st.markdown('<div class="brand">AbhiLekh</div><div class="eyebrow">FIELD REVIEW SYSTEM</div>', unsafe_allow_html=True)
        st.divider()
        role_label = st.radio("Workspace", ["Analyst", "Authority"], horizontal=True)
        role = "analyst" if role_label == "Analyst" else "authority"
        actor_options = ANALYSTS if role == "analyst" else AUTHORITIES
        default_actor = "R. Mehta" if role == "analyst" else "P. Rao"
        actor = st.selectbox("Reviewer", actor_options, index=actor_options.index(default_actor))
        if role == "analyst":
            view = st.radio("Workspace views", ["Flag queue", "Audit trail", "Monthly actions"])
        else:
            view = st.radio("Workspace views", ["Referred flags", "Monthly actions"])
        st.divider()
        st.caption("Nagpur Municipal Corporation")
        st.caption("Demonstration data · identity is simulated")

    page_title = "Flag review desk" if role == "analyst" else "Authority validation"
    st.markdown(
        f'<div class="portal-header"><div><div class="eyebrow">NAGPUR · URBAN CHANGE MONITORING</div><h1>{page_title}</h1><div style="color:#77847a;font-size:.82rem">Review satellite-screening candidates and retain a traceable case record.</div></div><div class="portal-header-note">PILOT ENVIRONMENT · DEMO DATA</div></div>',
        unsafe_allow_html=True,
    )

    if view == "Monthly actions":
        show_monthly_report()
        return
    if view == "Audit trail":
        st.subheader("All audit events")
        audit_rows = list_audit()
        if audit_rows:
            frame = pd.DataFrame([
                {"When": datetime.fromisoformat(str(row["created_at"]).replace("Z", "+00:00")).strftime("%d %b %Y %H:%M UTC"),
                 "Case": row["flag_reference"], "Event": row["action"].replace("_", " "),
                 "Actor": row["actor"], "Detail": f"{row['summary']}{' · ' + row['note'] if row['note'] else ''}"}
                for row in audit_rows
            ])
            st.dataframe(frame, hide_index=True, width="stretch")
        else:
            st.info("No audit events have been recorded.")
        return

    flags = list_flags(authority=role == "authority")
    needs_review = sum(flag["status"] in ("new", "triage") for flag in flags)
    with_authority = sum(flag["status"] in ("assigned", "authority_review", "field_visit") for flag in flags)
    high_priority = sum(flag["priority"] == "high" and flag["status"] not in DECIDED_STATUSES for flag in flags)
    awaiting = sum(flag["status"] in ("authority_review", "field_visit") for flag in flags)
    decided = sum(flag["status"] in ("action_taken", "not_illegal") for flag in flags)
    action_taken = sum(flag["status"] == "action_taken" for flag in flags)
    metrics = st.columns(4 if role == "analyst" else 3)
    if role == "analyst":
        metrics[0].metric("Needs review", needs_review)
        metrics[1].metric("With authority", with_authority)
        metrics[2].metric("High priority", high_priority)
        metrics[3].metric("Total flags", len(flags))
    else:
        metrics[0].metric("Awaiting decision", awaiting)
        metrics[1].metric("Reviewed", decided)
        metrics[2].metric("Action taken", action_taken)

    if role == "analyst":
        action_tools = st.columns(2, gap="small")
        with action_tools[0]:
            show_create_flag(actor)
        with action_tools[1]:
            show_detector_import(actor)
    search_column, filter_column = st.columns([2, 1])
    query = search_column.text_input("Search cases", placeholder="Reference, zone, address, or signal")
    status_filter = "All flags"
    if role == "analyst":
        status_filter = filter_column.selectbox("Status filter", ["All flags", "Needs review", "With authority", "Decided"])
    filtered = [flag for flag in flags if query.lower() in searchable_for(flag) and (
        status_filter == "All flags"
        or status_filter == "Needs review" and flag["status"] in ("new", "triage")
        or status_filter == "With authority" and flag["status"] in ("assigned", "authority_review", "field_visit")
        or status_filter == "Decided" and flag["status"] in DECIDED_STATUSES
    )]
    if role == "authority":
        st.caption(f"{len(flags)} referred case(s), including completed decisions.")
    if not filtered:
        st.info("No cases match this search and filter.")
        return
    options = [str(flag["id"]) for flag in filtered]
    selected_key = "analyst_selected_flag" if role == "analyst" else "authority_selected_flag"
    if st.session_state.get(selected_key) not in options:
        st.session_state[selected_key] = options[0]
    selected_id = st.session_state[selected_key]
    selected = get_flag(selected_id)
    if role == "analyst":
        queue_column, detail_column, history_column = st.columns([0.92, 1.95, 1.08], gap="small")
    else:
        queue_column, detail_column = st.columns([0.9, 2.1], gap="medium")
        history_column = None

    with queue_column:
        with st.container(border=True):
            st.markdown("#### Case register" if role == "analyst" else "#### Referred cases")
            st.caption(f"{len(filtered)} shown · select a case to inspect")
            with st.container(height=660, border=False):
                for flag in filtered:
                    is_selected = flag["id"] == selected_id
                    label = (
                        f"{flag['reference']}  ·  {str(flag['priority']).upper()}\n"
                        f"{flag['zone_name']}\n"
                        f"{STATUS_LABELS.get(str(flag['status']), str(flag['status']))}  ·  {flag['signal_label']}"
                    )
                    if st.button(
                        label,
                        key=f"case_{role}_{flag['id']}",
                        type="primary" if is_selected else "secondary",
                        width="stretch",
                    ):
                        st.session_state[selected_key] = str(flag["id"])
                        st.rerun()

    if selected:
        with detail_column:
            with st.container(border=True):
                show_flag_details(selected, actor, role, include_history=role == "authority")
        if history_column is not None:
            with history_column:
                with st.container(border=True):
                    st.markdown("#### Case history")
                    st.caption("Append-only activity")
                    show_case_history(str(selected["id"]))


def searchable_for(flag: dict[str, object]) -> str:
    return " ".join(str(flag[key]) for key in ("reference", "zone_name", "address", "signal_label")).lower()


if __name__ == "__main__":
    main()