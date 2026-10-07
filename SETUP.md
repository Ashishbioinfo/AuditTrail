# AbhiLekh

Streamlit flag-review and authority-validation portal for illustrative urban-change screening cases.

## Local setup

Requirements: Python 3.11+.

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run streamlit_app.py
```

The app creates and seeds `backend/data/flags.db` on first run. Set `ABHILEKH_DB_PATH` to use another database location.

## Streamlit Community Cloud

Push this repository to GitHub, create an app in Streamlit Community Cloud, select the repository and branch, and set the main file path to `streamlit_app.py`. The root `requirements.txt` installs the Streamlit dependencies.

## Workflow

1. Review illustrative flags in the analyst queue and search/filter by reference, zone, address, signal, and status.
2. Review the mapped location, scene dates, evidence summary, and estimated area.
3. Assign a reviewer and priority, route for authority review or field visit, or record an analyst outcome.
4. Add notes. Changes are appended to the audit trail with actor and UTC timestamp.
5. Switch to the Authority workspace to review referred flags. Authority reviewers choose **Action taken** or **Not illegal** and provide a required comment.
6. Attach permit, inspection, or decision evidence to a referred case in the Authority workspace. Files up to 15 MB are stored in SQLite, downloadable from the case, and recorded in the append-only history.
7. View monthly decision totals or inspect the global audit trail.

## Import anomalies from Construction Watch

1. In the `Ai Detection For the Illigal Construction` project, load T1/T2 imagery for a configured zone and select a comparison layer.
2. Under **Candidate locations**, choose **Export candidates to AbhiLekh**. The CSV includes a stable source ID, candidate type, coordinates, estimated area, scene dates/IDs, and screening notes.
3. In this portal's Analyst workspace, open **Import anomalies from Construction Watch**, upload the downloaded CSV, and select **Import detections**.
4. Imported candidates enter the analyst queue as new flags. Re-importing the same export skips previously imported source IDs.

The handoff is a CSV export/import, not a live connection between the two Streamlit apps. A candidate is a screening signal only and is not a verified building or legal finding.

Seed records are sample data, not real detections or verified violations. Production imagery should come from an approved evidence pipeline with source and scene provenance.

## Data and deployment

- Streamlit reads and writes SQLite directly; the existing FastAPI service under `backend/` is not required to run this app.
- The detector project remains separate and must be deployed independently if hosted; its CSV export is the integration boundary.
- SQLite defaults to `backend/data/flags.db` and is created/seeded on first app start.
- SQLite triggers reject updates/deletes on audit events. Flag changes and corresponding audit entries are committed in one transaction.
- Authority attachments are held as append-only SQLite BLOB records. They increase the database size and share its durability limits.
- Streamlit Community Cloud's local filesystem is not durable storage. Use a managed database before relying on persistent production records; the app currently uses SQLite and `ABHILEKH_DB_PATH` only changes its local file location.

## Production boundary

This is a demonstration, not an authority-ready deployment. The actor selector is simulated identity, not authentication. Before external sharing, add verified organization sign-in and role authorization, durable managed storage, backups/retention, and deployment monitoring. Screening output is not a legal determination; authorized staff must validate permits and evidence.