# AI-Powered Assignment Feedback Tool

A FastAPI and React application for assignment uploads, rubric-based AI grading,
and teacher review. Authentication remains application-owned JWT authentication;
Supabase Auth is not used.

## Stack

- Frontend: React, TypeScript, Tailwind CSS, Vite
- Backend: FastAPI, SQLAlchemy 2.x, PostgreSQL
- Database and private file storage: Supabase
- LLM: Groq, with a local mock fallback
- Parsing: PyMuPDF, python-docx, Pillow, Tesseract OCR

## Submission verification

Stage 0 checks readability and assignment relevance before classification and
grading. High-confidence mismatches are held so a student can replace the file
or the assignment's teacher can override the decision with an audited reason.
Partial matches and verifier outages are graded with a visible warning.

`GROQ_MODEL_VERIFY` configures the fast verification model. It and
`GROQ_MODEL_CLASSIFY`, `GROQ_MODEL_GRADE_FAST`, and
`GROQ_MODEL_GRADE_REASONING` can be configured through environment variables.
If `GROQ_API_KEY` is empty, the verifier reports `unverified` and the existing
mock grading path can be used. Verification thresholds and rate limits are
environment-configurable; see [.env.example](./.env.example).

## Supabase setup

1. Create a Supabase project and set a strong database password.
2. In **Connect**, choose the **Session pooler** and port **5432**. Copy its
   connection URL into `DATABASE_URL`. The backend normalizes `postgres://`,
   uses the psycopg2 driver, and enforces `sslmode=require`.
   If you manually insert a database password into the URL, percent-encode
   reserved characters such as `@`, `:`, `/`, and `#` first. Prefer the URL
   copied from Supabase and replace only its password with an encoded value.
3. In **Storage**, create a private bucket named `assignment-submissions` (or
   set `SUPABASE_BUCKET` to another private bucket name). Do not add public read
   policies or expose the service-role key to the frontend.
4. Copy `.env.example` to `.env` for local development and fill in the Supabase
   Session Pooler URL, `JWT_SECRET`, Supabase URL, bucket, and the
   backend-only service-role key. Set `CORS_ORIGINS` to exact comma-separated
   origins; local defaults are the Vite localhost origins shown in the example.
5. Install and start the backend:

   ```powershell
   cd backend
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   uvicorn main:app --reload
   ```

   The first startup creates missing tables, applies additive PostgreSQL
   migrations, and enables Row Level Security on every application table. The
   health endpoint is `GET /health`.

### RLS verification

In the Supabase SQL editor, verify every application table is protected:

```sql
SELECT schemaname, tablename, rowsecurity
FROM pg_tables
WHERE schemaname = 'public'
  AND tablename IN (
    'users', 'assignments', 'submissions', 'verification_attempts',
    'evaluations', 'rubrics', 'feedback'
  )
ORDER BY tablename;
```

Every returned row should have `rowsecurity = true`. The application creates no
RLS policies, so the public anon key cannot query application rows. The backend
uses its PostgreSQL connection role and does not use the Supabase Data API for
database access.

## Render deployment

Deploy from the repository root using [render.yaml](./render.yaml). Set:

- `DATABASE_URL`: Supabase Session Pooler URL (port 5432)
- `PYTHON_VERSION`: `3.12.10` (the Docker image is pinned to the same Python version)
- `JWT_SECRET`: long random signing secret
- `GROQ_API_KEY`: optional Groq key (leave unset for mock operation)
- `CORS_ORIGINS`: exact deployed frontend origin(s), comma-separated
- `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_BUCKET`

The Docker image installs Tesseract and the English language pack, runs as a
non-root user, and binds Uvicorn to Render's `$PORT`. Uploaded files are stored
in the private Supabase Storage bucket, not on Render's ephemeral filesystem.
`/health` checks PostgreSQL and returns 503 when the database is unavailable.
The Render service must use the repository's **Docker** runtime so the image
installs Tesseract and uses the pinned Python version. If an existing Render
service was created with the native Python runtime, update it to the Blueprint's
Docker service (or recreate it from `render.yaml`); setting `PYTHON_VERSION`
alone does not install Tesseract. A `.env` file is only for local development;
Render settings are read from the service's environment variables.

To test a configured database connection locally without printing credentials,
run this from `backend` (where the local `.env` file is normally loaded):

```powershell
python ..\scripts\check_db.py
```

## MySQL data transfer

The repository's previous local development database contains existing records.
The one-off [scripts/migrate_mysql_to_supabase.py](./scripts/migrate_mysql_to_supabase.py) utility copies those
records and their related upload files while preserving IDs. It is intentionally
not run automatically; review its dry-run output and take a database backup
before choosing to run it. It requires `MYSQL_DATABASE_URL`,
`DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, and
`SUPABASE_BUCKET`. Set `MYSQL_DATABASE_URL` in `mysql+pymysql://` form. Install
`pymysql` only in the migration environment when using that utility; it is not
an application dependency. With the backend virtual environment active, run
the following from `backend`; the default command is a read-only dry run:

```powershell
pip install pymysql
python ..\scripts\migrate_mysql_to_supabase.py
```

Only after reviewing its source-row counts and backing up both systems, use
`python ..\scripts\migrate_mysql_to_supabase.py --apply`; it requires typing
`MIGRATE` before writing. This project task has not executed that command.

## Tests

Run backend tests from `backend`:

```powershell
pytest
```

To exercise the PostgreSQL-specific migration and integration tests, set
`TEST_POSTGRES_URL` to a dedicated, disposable PostgreSQL database with `test`
in its database name. The integration fixture removes only application tables
from that explicitly designated test database. Storage tests use a mocked
Supabase client. Set `DATABASE_URL` to a valid PostgreSQL URL before importing
the backend test modules.
