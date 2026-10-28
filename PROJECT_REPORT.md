# AI-Powered Assignment Feedback Tool — Project Report

**Report date:** 15 October 2026
**Project repository:** `piyush814325/Ai-powered-assignment-feedback-tool`

## 1. Executive summary

The project is a web application for creating assignments, collecting student
submissions, checking submission relevance, grading work against a rubric, and
supporting teacher review. The frontend is built with React, TypeScript, Tailwind
CSS, and Vite. The API uses FastAPI and SQLAlchemy with PostgreSQL on Supabase.
Private uploaded files are stored in Supabase Storage. Groq is used for AI
classification, verification, and grading when configured.

The work completed so far includes the verification gate, persistent private
file storage, PostgreSQL/Supabase setup, teacher and student workflow
improvements, and Render/Vercel deployment configuration. Tests and build checks
have been run locally. A complete live production workflow has not yet been
verified against the deployed Render and Vercel services.

## 2. Project goals and capabilities

- Give teachers a way to manage assignments and rubrics.
- Let students upload work and receive grading feedback.
- Avoid confidently grading work that is clearly unrelated to its assignment.
- Let teachers review, edit, or override AI results where appropriate.
- Keep application data in PostgreSQL and uploaded files in private persistent
  storage.
- Deploy the frontend and backend independently while keeping secrets on the
  server.

## 3. Technology stack

| Area | Technology |
|---|---|
| Frontend | React, TypeScript, Tailwind CSS, Vite |
| Backend API | Python, FastAPI, Uvicorn |
| Data access | SQLAlchemy 2.x |
| Database | Supabase PostgreSQL |
| Uploaded file storage | Private Supabase Storage bucket |
| Authentication | Application-managed JWT; Supabase Auth is not used |
| AI services | Groq API, with mock behavior available for local development |
| Document parsing | PyMuPDF, python-docx, Pillow, Tesseract OCR |
| Frontend hosting | Vercel |
| Backend hosting | Render Docker web service |

## 4. Implemented application workflows

### 4.1 Authentication and roles

- The application retains its own JWT-based authentication.
- User roles distinguish student and teacher access.
- API routes enforce role and ownership checks for relevant actions.
- Authentication and database secrets are intended to be configured through
  environment variables and are not frontend configuration.

### 4.2 Assignments and rubric grading

- Teachers can create and manage assignments with allowed file types and rubric
  criteria.
- Assignment deletion removes assignments only when there are no submissions;
  assignments with submissions cannot be permanently deleted through that
  operation.
- Submissions are evaluated against rubric criteria and receive criterion-level
  scores, feedback, evidence, and an overall result.
- Classification informs grading model selection, including fast and reasoning
  model configuration.

### 4.3 Submission verification gate

Submission processing includes a Stage 0 verification step before
classification and grading:

1. The backend reads the uploaded object and extracts document text, code, or
   OCR text.
2. Deterministic checks detect insufficient readable content and duplicate
   submissions. A content hash can also provide evidence that identical content
   was submitted to a different assignment.
3. When configured, a Groq model checks whether the work appears relevant to the
   assignment.
4. A high-confidence mismatch is marked as needing attention instead of being
   graded automatically. Students can replace the file, and the assignment
   teacher can override the decision with a required reason.
5. Partial matches and verification outages fail open to grading, while keeping
   a warning/result for review.

Verification output, model metadata, reasons, and machine-readable failure
information are persisted with the submission. Verification and grading model
IDs and verification thresholds are configurable.

### 4.4 Student and teacher experience

- Students receive upload progress/status feedback and can replace a file when
  verification requires attention.
- Verification outcomes and warnings are surfaced without displaying raw model
  output.
- Teachers can inspect verification details, review grading results, rerun
  verification, and override a rejected verification with an audit reason.
- Teachers can review submissions and update evaluation details through the
  existing review workflow.

## 5. Data, storage, and privacy

- Supabase PostgreSQL is the application database.
- The application creates missing tables and applies additive,
  rerunnable migrations through the existing migration module.
- Row Level Security is enabled on application tables. The intended setup uses
  no public policies for those application records; the backend connects to the
  database directly.
- Uploaded files are saved under generated object keys in a private Supabase
  Storage bucket. Files are accessed through the backend’s authorized file
  routes/storage layer, not public bucket URLs.
- Upload size and file-type restrictions are enforced server-side.
- The Supabase service-role key is backend-only and must never be exposed in a
  Vercel `VITE_` variable.
- `.env.example` contains placeholders; real credentials belong in local
  ignored `.env` files or hosting-provider secret settings.

## 6. Deployment configuration

### 6.1 Render backend

The repository includes a Render Blueprint and Dockerfile. The Docker image:

- Uses Python 3.12.10.
- Installs Tesseract and its English language pack.
- Runs Uvicorn on Render’s `$PORT`.
- Runs as a non-root user.
- Exposes `GET /health` as the Render health check; the route checks PostgreSQL
  with `SELECT 1`.

Render service configuration must provide `DATABASE_URL`, `JWT_SECRET`,
`SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_BUCKET`, and
`CORS_ORIGINS`. `GROQ_API_KEY` is needed for real Groq-backed evaluation;
without it, configured mock/fail-open behavior applies.

### 6.2 Vercel frontend

The frontend is intended to be deployed as a Vite project with the `frontend`
directory as its project root. Set the Vercel build-time variable
`VITE_API_URL` to the public Render backend URL, without a trailing slash or
extra `/api` prefix.

### 6.3 Required production settings and current deployment findings

- `DATABASE_URL` must use Supabase’s **Session Pooler** connection string on
  port **5432**, with the pooler username in the form `postgres.<project-ref>`.
  Render cannot reach Supabase’s IPv6-only direct host (`db.<project-ref>.supabase.co`).
- The most recent Render startup log provided during development showed a
  connection attempt to the direct `db.*.supabase.co` host and the error
  `Network is unreachable`. This is a configuration problem, not a grading or
  migration failure. The Render `DATABASE_URL` must be replaced with the Session
  Pooler URL.
- The browser’s CORS error showed the Vercel origin
  `https://ai-powered-assignment-feedback-tool-orpin.vercel.app` was not allowed.
  Add that exact origin to the backend’s Render `CORS_ORIGINS` value (plus any
  other exact production/custom-domain origins), then restart/redeploy Render.
- The submitted Render log showed a native Python Uvicorn command. For the
  repository’s OCR-enabled configuration, the Render service should use the
  repository’s Docker Blueprint so Tesseract is installed. The parser now
  skips OCR gracefully if Tesseract is not available, but scanned/image-only
  work may then be unverifiable.
- These hosting-provider environment settings must be confirmed in their
  dashboards; committing configuration files alone does not set secret values.

## 7. Database connectivity diagnostics

Recent backend changes improve troubleshooting by:

- Normalizing `postgres://` URLs to the psycopg2 SQLAlchemy driver format and
  ensuring SSL mode is required.
- Stripping common wrapping quotes/whitespace from `DATABASE_URL`.
- Configuring pre-ping, a 30-minute pool recycle, a small pool, and a
  10-second connection timeout.
- Logging a sanitized connection target (host, port, database, username
  prefix, SSL state, and host kind) without logging the password or full URL.
- Classifying common DNS/network, authentication, pooler tenant, timeout, and
  SSL failures into actionable hints.
- Retrying database startup up to five times with short backoff.
- Preserving the underlying exception as the cause of startup failure.

The helper `scripts/check_db.py` runs a safe `SELECT 1` connectivity check and
prints a sanitized success or failure result. Run it from the `backend`
directory so the local `.env` is loaded.

## 8. Testing and verification to date

The latest recorded local validation for the Render startup and OCR changes:

- Backend pytest suite: **37 passed, 1 skipped**.
- The skipped test requires a dedicated disposable PostgreSQL database through
  `TEST_POSTGRES_URL`; it was not run against a production database.
- Python syntax compilation completed successfully.
- `pip check` reported no broken requirements.
- The database connectivity helper successfully ran `SELECT 1` with the local
  environment. Its reported host was the Supabase direct host, which is
  reachable from that local environment but must not be used for Render.
- Earlier frontend production builds completed successfully.
- Mocked storage, health endpoint behavior, submission verification, OCR
  behavior, and assignment deletion have focused tests.

No end-to-end test of the current live Vercel frontend against a successfully
started Render backend is recorded yet. The Render database URL and CORS
environment settings must be fixed and checked before that acceptance test.

## 9. Migration utility and data-transfer status

The repository contains a one-off
`scripts/migrate_mysql_to_supabase.py` utility for transferring prior local
MySQL records and related files. It is separate from the deployed app and is
not run automatically. It has not been run as part of the project work
described here. Any real data transfer should be preceded by backups and
review of the script’s dry-run counts.

## 10. Remaining work / deployment checklist

- [ ] Replace Render `DATABASE_URL` with the Supabase Session Pooler URL on
      port 5432; verify the username uses `postgres.<project-ref>`.
- [ ] Confirm Render service uses the Docker Blueprint/Dockerfile.
- [ ] Set `CORS_ORIGINS` to the exact Vercel production origin and any custom
      domain origins.
- [ ] Confirm Vercel `VITE_API_URL` points to the Render service URL.
- [ ] Redeploy/restart Render, then confirm `/health` returns HTTP 200.
- [ ] Test registration/login from Vercel, assignment creation, upload,
      verification, grading, private file access, and teacher review.
- [ ] If desired, run PostgreSQL integration tests against a dedicated
      disposable PostgreSQL test database (never a production database).
- [ ] If legacy MySQL records must be retained, review backups and the
      migration utility’s dry run before explicitly applying it.

## 11. Recent implementation commits

- `b645088` — Added assignment verification, Supabase storage/database
  integration, and deployment-related features.
- `fde7f68` — Added Render/Supabase startup diagnostics, URL handling, Python
  pinning, OCR fallback, and database connectivity checks.
