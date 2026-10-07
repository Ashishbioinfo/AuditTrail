# Abhilekh

Standalone flag review and authority-validation portal, separate from the Sentinel-2 monitoring prototype.

## Local pilot

Requirements: Node.js 20.19+ (or 22.12+) and Python 3.11+.

In PowerShell, from this directory, create the backend environment and install the API dependencies:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

Start the API in one terminal:

```powershell
.\.venv\Scripts\python.exe -m uvicorn main:app --app-dir backend --reload --port 8000
```

Start the UI in another terminal:

```powershell
npm install
npm run dev
```

Open the Vite URL, normally `http://localhost:5173`. API health/docs: `http://localhost:8000/api/health` and `http://localhost:8000/docs`.

## Workflow

1. Review illustrative flags in the queue and search/filter by ID, zone, signal, and status.
2. Open a case to review its mapped location, scene dates, evidence summary, and estimated area.
3. Set an assignee/priority, route for authority review or field visit, or record a review outcome.
4. Add notes. Each action is appended to the audit trail with actor and UTC timestamp.
5. Switch to the Authority portal to see referred flags. Authority reviewers choose **Take action** or **Not illegal** and must provide a comment; the API records the named actor, role, comment, outcome, and timestamp.
6. The Authority portal and Corporation portal each have a monthly report counting action-taken and not-illegal outcomes from audit timestamps.
7. Use the global audit view to inspect events across all cases.

Seed records are sample data, not real detections or verified violations. Scene cards currently show metadata placeholders; production imagery must be attached from an approved evidence pipeline with source and scene provenance.

## API and data

- `GET /api/flags`, `POST /api/flags`
- `PATCH /api/flags/{id}` for status, assignee, and priority updates
- `GET /api/flags/{id}/audit`, `GET /api/audit`
- `POST /api/flags/{id}/notes`
- Authority: `GET /api/authority/flags`, `GET /api/authority/flags/{id}/audit`, `POST /api/authority/flags/{id}/decision`
- Monthly metrics: `GET /api/authority/metrics/monthly`, `GET /api/corporation/metrics/monthly`
- SQLite is stored at `backend/data/flags.db` and is created/seeded on first API start.
- SQLite triggers reject updates/deletes on audit events. A flag change and its audit event are committed in one transaction.

## Production boundary

This is a local pilot, not an authority-ready deployment. The actor selector and `X-Role` header are simulated identity, not authentication, and can be spoofed. Before external sharing, validate organization SSO tokens in the API and derive user/role from the verified identity instead of request headers. Also add HTTPS, managed PostgreSQL/PostGIS, object storage for approved evidence, backups/retention, rate limiting, and deployment monitoring. Screening output is not a legal determination; authorized staff must validate permits and evidence.