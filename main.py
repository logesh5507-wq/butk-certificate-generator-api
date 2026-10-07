from __future__ import annotations

import io
import os
import re
import sqlite3
import uuid
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.certificate import create_certificate_pdf

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("CERTIFICATE_DATA_DIR", str(BASE_DIR / "data")))
CERTIFICATES_DIR = DATA_DIR / "certificates"
DB_PATH = Path(os.getenv("CERTIFICATE_DB_PATH", str(DATA_DIR / "certificates.db")))

app = FastAPI(
    title="Bulk Certificate Generator API",
    description="Create bulk certificate jobs, track progress, and download generated PDF certificates.",
    version="1.0.0",
)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class RecipientInput(BaseModel):
    # Optional fields let the API report an invalid recipient without rejecting the entire batch.
    name: str | None = None
    email: str | None = None
    course: str | None = None
    event_name: str | None = None
    issue_date: str | None = None


class CreateJobRequest(BaseModel):
    recipients: list[RecipientInput] = Field(min_length=1, max_length=500)
    organization: str = Field(default="Example Organization", min_length=1, max_length=120)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_db() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CERTIFICATES_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=30)
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    with get_db() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                total INTEGER NOT NULL,
                processed INTEGER NOT NULL DEFAULT 0,
                succeeded INTEGER NOT NULL DEFAULT 0,
                failed INTEGER NOT NULL DEFAULT 0,
                organization TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS recipients (
                id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL,
                name TEXT,
                email TEXT,
                status TEXT NOT NULL,
                error TEXT,
                certificate_path TEXT,
                FOREIGN KEY(job_id) REFERENCES jobs(id)
            )
        """)


@app.on_event("startup")
def startup() -> None:
    init_db()


def validate_recipient(item: RecipientInput) -> tuple[bool, str | None, dict[str, str]]:
    values = {
        "name": (item.name or "").strip(),
        "email": (item.email or "").strip(),
        "course": (item.course or "").strip(),
        "event_name": (item.event_name or "").strip(),
        "issue_date": (item.issue_date or date.today().isoformat()).strip(),
    }
    if not values["name"]:
        return False, "name is required", values
    if not values["email"] or not EMAIL_RE.match(values["email"]):
        return False, "a valid email is required", values
    if not values["course"]:
        return False, "course is required", values
    if not values["event_name"]:
        return False, "event_name is required", values
    try:
        date.fromisoformat(values["issue_date"])
    except ValueError:
        return False, "issue_date must use YYYY-MM-DD format", values
    return True, None, values


def process_job(job_id: str, recipients: list[dict[str, Any]], organization: str) -> None:
    with get_db() as db:
        db.execute("UPDATE jobs SET status=?, updated_at=? WHERE id=?", ("processing", utc_now(), job_id))
        db.commit()

    for raw in recipients:
        recipient_id = raw["id"]
        item = RecipientInput(**raw["input"])
        valid, error, values = validate_recipient(item)
        if not valid:
            with get_db() as db:
                db.execute(
                    "UPDATE recipients SET status=?, error=? WHERE id=?",
                    ("failed", error, recipient_id),
                )
                db.execute(
                    "UPDATE jobs SET processed=processed+1, failed=failed+1, updated_at=? WHERE id=?",
                    (utc_now(), job_id),
                )
                db.commit()
            continue

        try:
            filename = f"{recipient_id}.pdf"
            path = CERTIFICATES_DIR / job_id / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            create_certificate_pdf(
                output_path=path,
                recipient_name=values["name"],
                course=values["course"],
                event_name=values["event_name"],
                issue_date=values["issue_date"],
                organization=organization,
            )
            with get_db() as db:
                db.execute(
                    "UPDATE recipients SET status=?, certificate_path=?, error=NULL WHERE id=?",
                    ("completed", str(path), recipient_id),
                )
                db.execute(
                    "UPDATE jobs SET processed=processed+1, succeeded=succeeded+1, updated_at=? WHERE id=?",
                    (utc_now(), job_id),
                )
                db.commit()
        except Exception as exc:  # isolate a single certificate failure from the rest of the batch
            with get_db() as db:
                db.execute(
                    "UPDATE recipients SET status=?, error=? WHERE id=?",
                    ("failed", f"Certificate generation failed: {type(exc).__name__}", recipient_id),
                )
                db.execute(
                    "UPDATE jobs SET processed=processed+1, failed=failed+1, updated_at=? WHERE id=?",
                    (utc_now(), job_id),
                )
                db.commit()

    with get_db() as db:
        row = db.execute("SELECT failed FROM jobs WHERE id=?", (job_id,)).fetchone()
        final_status = "completed_with_errors" if row and row["failed"] else "completed"
        db.execute("UPDATE jobs SET status=?, updated_at=? WHERE id=?", (final_status, utc_now(), job_id))
        db.commit()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/v1/certificate-jobs", status_code=202)
def create_job(payload: CreateJobRequest, background_tasks: BackgroundTasks) -> dict[str, Any]:
    init_db()
    job_id = str(uuid.uuid4())
    now = utc_now()
    prepared: list[dict[str, Any]] = []
    with get_db() as db:
        db.execute(
            "INSERT INTO jobs(id,status,total,processed,succeeded,failed,organization,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (job_id, "queued", len(payload.recipients), 0, 0, 0, payload.organization.strip(), now, now),
        )
        for item in payload.recipients:
            recipient_id = str(uuid.uuid4())
            prepared.append({"id": recipient_id, "input": item.model_dump()})
            db.execute(
                "INSERT INTO recipients(id,job_id,name,email,status) VALUES(?,?,?,?,?)",
                (recipient_id, job_id, item.name, item.email, "queued"),
            )
        db.commit()

    background_tasks.add_task(process_job, job_id, prepared, payload.organization.strip())
    return {
        "job_id": job_id,
        "status": "queued",
        "total": len(prepared),
        "status_url": f"/api/v1/certificate-jobs/{job_id}",
    }


@app.get("/api/v1/certificate-jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    with get_db() as db:
        job = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not job:
            raise HTTPException(status_code=404, detail="Certificate job not found")
        recipients = db.execute(
            "SELECT id,name,email,status,error FROM recipients WHERE job_id=? ORDER BY rowid",
            (job_id,),
        ).fetchall()
    result = dict(job)
    result["progress_percent"] = round((result["processed"] / result["total"]) * 100) if result["total"] else 100
    result["recipients"] = [dict(r) for r in recipients]
    result["download_url"] = f"/api/v1/certificate-jobs/{job_id}/download"
    return result


@app.get("/api/v1/certificate-jobs/{job_id}/certificates/{recipient_id}")
def download_certificate(job_id: str, recipient_id: str) -> FileResponse:
    with get_db() as db:
        row = db.execute(
            "SELECT certificate_path,name FROM recipients WHERE id=? AND job_id=? AND status='completed'",
            (recipient_id, job_id),
        ).fetchone()
    if not row or not row["certificate_path"]:
        raise HTTPException(status_code=404, detail="Certificate not found or not generated")
    path = Path(row["certificate_path"])
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Certificate file is missing")
    safe_name = re.sub(r"[^A-Za-z0-9_-]+", "_", row["name"] or "participant").strip("_") or "participant"
    return FileResponse(path, media_type="application/pdf", filename=f"{safe_name}_certificate.pdf")


@app.get("/api/v1/certificate-jobs/{job_id}/download")
def download_all_certificates(job_id: str) -> StreamingResponse:
    with get_db() as db:
        job = db.execute("SELECT id FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not job:
            raise HTTPException(status_code=404, detail="Certificate job not found")
        rows = db.execute(
            "SELECT name,certificate_path FROM recipients WHERE job_id=? AND status='completed'",
            (job_id,),
        ).fetchall()
    if not rows:
        raise HTTPException(status_code=404, detail="No generated certificates are available yet")
    memory_file = io.BytesIO()
    with zipfile.ZipFile(memory_file, "w", zipfile.ZIP_DEFLATED) as archive:
        for row in rows:
            path = Path(row["certificate_path"])
            if path.is_file():
                safe_name = re.sub(r"[^A-Za-z0-9_-]+", "_", row["name"] or "participant").strip("_") or "participant"
                archive.write(path, arcname=f"{safe_name}_{path.name}")
    memory_file.seek(0)
    return StreamingResponse(
        memory_file,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="certificates_{job_id}.zip"'},
    )
