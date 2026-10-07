# Bulk Certificate Generator API

A Python + FastAPI backend that accepts one request containing many recipients, validates each recipient, generates PDF certificates from one predefined template, tracks job progress in SQLite, and lets clients download one certificate or a ZIP of all successful certificates.

## Features

- Bulk certificate jobs (up to 500 recipients per request).
- Per-recipient validation; one invalid record does not reject the entire batch.
- PDF certificate generation using ReportLab.
- SQLite relational storage for jobs and recipient results.
- Job status, progress percentage, success/failure counts, and per-recipient errors.
- Individual PDF download and ZIP download for all successful certificates.
- Automated tests for job creation, validation, generation, status/progress, failure isolation, and downloads.

## Requirements

- Python 3.10+
- pip

## Setup

```bash
python -m venv .venv
```

Activate the environment:

**Windows PowerShell**
```powershell
.\.venv\Scripts\Activate.ps1
```

**Windows Command Prompt**
```bat
.venv\Scripts\activate.bat
```

**macOS/Linux**
```bash
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

## Run the API

```bash
uvicorn app.main:app --reload
```

- Health check: http://127.0.0.1:8000/health
- Interactive API docs: http://127.0.0.1:8000/docs

SQLite database and generated files are stored under `data/` by default. Set `CERTIFICATE_DATA_DIR` and/or `CERTIFICATE_DB_PATH` to change the locations.

## Create a bulk generation job

Send `POST /api/v1/certificate-jobs` with JSON:

```json
{
  "organization": "Acme Learning",
  "recipients": [
    {
      "name": "Asha Kumar",
      "email": "asha@example.com",
      "course": "Python Fundamentals",
      "event_name": "Developer Workshop",
      "issue_date": "2026-10-07"
    },
    {
      "name": "Ravi Kumar",
      "email": "ravi@example.com",
      "course": "API Development",
      "event_name": "Developer Workshop",
      "issue_date": "2026-10-07"
    }
  ]
}
```

A job ID and status URL are returned. Generation is scheduled using FastAPI background tasks. For this small assignment, it runs in the same application process; for very large production workloads, replace it with a durable queue/worker such as Celery or RQ.

## API endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | Health check |
| POST | `/api/v1/certificate-jobs` | Submit a batch of recipients |
| GET | `/api/v1/certificate-jobs/{job_id}` | Read job status, progress, and recipient results |
| GET | `/api/v1/certificate-jobs/{job_id}/certificates/{recipient_id}` | Download one successful PDF |
| GET | `/api/v1/certificate-jobs/{job_id}/download` | Download a ZIP of successful PDFs |

Possible job statuses: `queued`, `processing`, `completed`, `completed_with_errors`.

Each recipient status is `queued`, `completed`, or `failed`. Invalid recipients are recorded as failures and processing continues. Certificate-generation exceptions are isolated per recipient. The API intentionally returns the validation error for each failed recipient in the job status response.

## Test

```bash
pytest -v
```

## Design decisions

- **FastAPI:** automatic OpenAPI documentation and request parsing.
- **SQLite:** lightweight relational database requiring no separate database server.
- **ReportLab:** creates PDF certificates with one fixed template; no template editor is required.
- **Per-recipient validation:** allows valid recipients to succeed even when some input rows are invalid.
- **BackgroundTasks:** keeps the submission endpoint responsive while the batch is processed. This is adequate for the assignment/demo; a durable queue is more appropriate for high-volume production workloads.
- **ZIP response:** streams a bundle of available successful PDFs without requiring a separate ZIP file to be stored.

## Example status response (shortened)

```json
{
  "job_id": "your-job-id",
  "status": "completed_with_errors",
  "total": 2,
  "processed": 2,
  "succeeded": 1,
  "failed": 1,
  "progress_percent": 100
}
```

## Notes

This is a starter assignment implementation. Before production use, add authentication/authorization, rate limits, retention cleanup, structured logging, and a durable worker queue.
