Safaricom Ethiopia NOC Shift Portal
===================================

Architecture
------------
- FastAPI Python backend
- PostgreSQL database (required; CSV files are retained only for legacy pages)
- SQLAlchemy data models and Alembic database migrations
- Excel .xlsx upload for Front Office, L2, shift handover, and seven-region records
- HttpOnly signed session cookie and server-side guest/operator/admin authorization
- Uploaded workbook contents and import audit logs are stored in PostgreSQL

Install Python dependencies
---------------------------
Python 3.10 or newer is required.

  pip install -r requirements.txt

Configure the database and secrets
----------------------------------
Create a PostgreSQL database and a dedicated database user. Keep credentials and
secrets in your deployment's secret manager/environment settings; do not commit them.

PowerShell examples (use your real values):

  $env:DATABASE_URL = 'postgresql+psycopg://portal_user:password@db-host:5432/noc_portal'
  $env:JWT_SECRET_KEY = 'replace-with-a-random-secret-at-least-32-characters-long'
  $env:COOKIE_SECURE = 'true'
  $env:INITIAL_ADMIN_USERNAME = 'your-admin-account'
  $env:INITIAL_ADMIN_EMAIL = 'admin@example.com'
  $env:INITIAL_ADMIN_FULL_NAME = 'Portal Administrator'
  $env:INITIAL_ADMIN_PASSWORD = 'use-a-unique-password-at-least-12-characters'

Generate a strong signing secret with:

  python -c "import secrets; print(secrets.token_urlsafe(48))"

For production, serve the portal only over HTTPS and keep COOKIE_SECURE=true.
For HTTP-only local testing, set COOKIE_SECURE=false in that shell only.
Set APP_ENV=production in production. Startup rejects the known local development
JWT, database, and bootstrap-admin credentials when production mode is enabled.
Set ALLOWED_HOSTS to the exact public hostname(s) used by the deployment. The Render
configuration includes its default service hostname; add any custom domain too.

Run the development stack
-------------------------
From the project directory, set up `.env` once by copying `.env.example` if you do not
already have a `.env` file. Then run the whole development stack with one command:

  docker compose up --build --remove-orphans

Compose starts PostgreSQL and the FastAPI app. The app applies Alembic migrations,
then starts Uvicorn with reload enabled and your project directory mounted into the
container. Python changes reload automatically. The app and database ports bind to
localhost only. Compose defaults to APP_ENV=development and uses local-only example
credentials; do not expose this stack publicly. The development compose file does not
start pgAdmin. Use `/healthz` for a database-aware readiness check; request IDs,
status codes, paths, and response times are written to the application log without
recording query strings or authentication tokens.

Open the portal at http://localhost:8000/ and API docs at http://localhost:8000/api-docs.
The first database startup creates the admin account from INITIAL_ADMIN_* in `.env`;
these bootstrap settings do not reset an existing account. The database stays in the
postgres_data volume. Stop the stack with Ctrl+C or `docker compose down`; do not add
`-v` unless you intend to erase the database.

Run the built-in regression suite from the project directory with:

  docker compose exec -T app python -m unittest discover -s tests -v

These tests exercise roster parsing and limits, login behavior and session cookies,
login throttling, and permission rules without writing to the configured database.

Run the browser-based UI checks from a development environment with:

  python -m pip install -r requirements-dev.txt
  python -m playwright install chromium
  python -m pytest ui_tests -q

These tests run the portal page with isolated API responses and verify creating a
Knowledge Hub post and retaining the selected theme after a reload. They do not use
the configured database or operational data. If browser downloads are unavailable,
set PLAYWRIGHT_CHROMIUM_EXECUTABLE to an installed Chrome or Chromium executable path.

To run the real-backend Knowledge Hub contract test, start its dedicated disposable
database and app (the app is available only on local port 8001):

  docker compose -p noc-portal-e2e -f compose.integration.yaml up -d integration-db integration-app
  .venv\Scripts\python.exe -m playwright install chromium
  $env:E2E_PORTAL_URL = "http://127.0.0.1:8001"
  $env:E2E_USERNAME = "testadmin"
  $env:E2E_PASSWORD = "IntegrationAdmin123!"
  .venv\Scripts\python.exe -m pytest ui_tests/test_knowledge_contract.py -q
  docker compose -p noc-portal-e2e -f compose.integration.yaml down -v --remove-orphans

The test signs in through the UI, creates and verifies an article using the real API,
then deactivates the test article. Run it only against this disposable local stack;
the test refuses non-local app URLs. The normal mocked UI suite skips this contract
test unless E2E_PORTAL_URL is explicitly set.

Run the HTTP integration suite against a separate disposable PostgreSQL database with:

  docker compose -p noc-portal-integration -f compose.integration.yaml run --build --rm integration-tests

The integration stack uses its own Compose project and never connects to the development
database. The suite resets only its dedicated test database before creating fixtures, so
the command can be rerun safely. Remove its temporary database afterward with:

  docker compose -p noc-portal-integration -f compose.integration.yaml down -v --remove-orphans

GitHub Actions runs the unit tests, mocked browser tests, PostgreSQL integration suite,
and real-backend browser contract test on pushes and pull requests. CI uses a disposable
database and test-only credentials; it does not use operational data or deployment
secrets.

Excel workbook format
---------------------
Use the administrator page to download the generated workbook template and then
upload a completed .xlsx file. The workbook must include these four sheets:

FrontOfficeShift columns:
  shift_date, shift_name, person_name, title, phone, email, is_primary

L2Support columns:
  shift_date, shift_name, domain, engineer_name, role, phone, email, ip, team_name

The L2Support `ip` column is optional for older workbooks.

ShiftHandover columns:
  shift_date, shift_name, start_time, end_time, next_shift_name, update_for_next_shift,
  operational_challenges, active_change_requests, planned_maintenance,
  active_field_teams, major_incidents, resolved_major_incidents,
  alarms_pending_resolution, closed_trouble_tickets, archived_handover_index

HandoverRegions columns:
  shift_date, shift_name, region_name, corrective_maintenance_count, notes

Allowed shift names are morning, afternoon, and night. L2 domains are
transmission, ran, power, and core. The legacy workbook values "PSCore & SDM"
and "pscore_sdm" are also accepted and imported as core.
Use a real Excel date or YYYY-MM-DD; the date is the date the shift starts
(the night shift may end the following calendar day). Each ShiftHandover row needs exactly seven
regions in HandoverRegions for the same date and shift, each listed exactly once:
East 1, East 2, West, North West, North East, North, and Afar. Region names are
matched without regard to capitalization and saved in this standard spelling.
List at most six active field teams in `active_field_teams`, one per line.
The following shift is validated in sequence: morning, afternoon, night, then morning.
Provide each shift's actual local start_time and end_time in 24-hour HH:MM format;
the system verifies an eight-hour duration, including an overnight shift. Incident,
alarm, ticket, and regional maintenance counts are whole numbers from 0 to 50.

An import validates the entire workbook before saving it. Importing a shift that
already exists replaces its roster and handover data as one database transaction.
Successful and validation-failed workbook imports are tracked. Re-importing a roster
replaces the existing matching roster data in a transaction. Uploads are limited to
10 MB; Excel files also have expanded-size and archive-entry limits. Excel sheets and
CSV imports are capped at 20,000 rows and 512 columns.

Front Office roster team labels are maintained by administrators in
`/admin.html` under Team label mappings. Uploads reject unregistered labels and
identify the offending workbook row. Each registered label has an optional
Power or Transmission challenge domain; the database enforces the allowed
domain values, and challenge access is resolved through the roster team's
foreign key rather than matching team-name text.

Roles and API
-------------
- guest: read operational data; cannot edit or upload documents
- operator: guest access plus submitting and acknowledging handovers; an administrator may grant
  content-edit and roster-upload permissions separately
- admin: full access, including Excel uploads, user management, and audit history
- every user can change their own password; this invalidates their previous sessions

Administrators manage the operator permissions from the User accounts table at
`/admin.html`. Roster-upload-authorized operators can access only the workbook
upload section; account management and audit history remain administrator-only.

All endpoints are documented in the authenticated API documentation at /api-docs.
Key endpoints:
  POST  /api/v1/auth/login
  POST  /api/v1/auth/logout
  GET   /api/v1/auth/me
  POST  /api/v1/auth/password
  GET   /api/v1/shifts?date=YYYY-MM-DD&shift_name=morning
  GET   /api/v1/shifts/{id}/front-office
  GET   /api/v1/shifts/{id}/l2-support
  GET   /api/v1/shifts/{id}/handover
  PUT   /api/v1/shifts/{id}/handover
  POST  /api/v1/shifts/{id}/handover/acknowledge
  GET/POST /api/v1/process
  PUT   /api/v1/process/{id}
  GET/POST /api/v1/knowledge-hub
  PUT   /api/v1/knowledge-hub/{id}
  GET   /api/v1/users
  POST  /api/v1/users
  PATCH /api/v1/users/{id}
  GET   /api/v1/uploads
  GET   /api/v1/uploads/template
  POST  /api/v1/uploads/excel
  GET   /api/v1/audit-logs

When updating an existing handover, process, or Knowledge Hub article, send the record's
`updated_at` value as `expected_updated_at`. An update without a revision receives HTTP
428; if another user saves first, the stale update receives HTTP 409 and must reload the
latest record before retrying.

Before production deployment
----------------------------
- Use PostgreSQL on a private network and a least-privilege database account.
- Configure HTTPS, secure secret storage, restricted network access, monitoring,
  backup/restore procedures, and a retention policy for uploaded workbooks.
- The app throttles sign-in failures (10 per account/address and 60 per address in a
  15-minute window) per process. This is a basic backstop; configure shared edge-level
  rate limiting and centralized log/alert monitoring for multi-worker or multi-instance
  production deployments.
- Configure database backups, restore drills, and uploaded-workbook retention in the
  database hosting environment; the application does not schedule backups itself.
- Run Alembic migrations as a deployment/release step before starting app workers.
- Configure trusted reverse-proxy headers at the deployment edge. Do not expose the
  development reload server to the public internet.


Project layout
--------------
- ui/pages/: HTML user interface pages
- ui/assets/portal-*.js: browser-side portal features
- main.py: environment loading and ASGI application entry point
- server/application.py: FastAPI application and router assembly
- server/lifecycle.py and server/middleware.py: startup and HTTP middleware
- server/controllers/: FastAPI HTTP controllers grouped by domain
- server/services/: application/business logic
- server/repositories/: database query and persistence operations
- server/config.py and server/database.py: settings and SQLAlchemy session setup
- server/models/: SQLAlchemy models
- server/schemas.py: API input and output schemas
- server/domain/: shared domain constants and normalization
- server/migrations/: Alembic environment and schema revisions
- server/alembic.ini: Alembic configuration
