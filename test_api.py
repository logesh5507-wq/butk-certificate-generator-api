import os
from pathlib import Path

from fastapi.testclient import TestClient
import app.main as main


def setup_client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(main, "CERTIFICATES_DIR", tmp_path / "data" / "certificates")
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "data" / "test.db")
    main.init_db()
    return TestClient(main.app)


def test_health(tmp_path, monkeypatch):
    client = setup_client(tmp_path, monkeypatch)
    assert client.get("/health").json() == {"status": "ok"}


def test_create_job_validation_status_and_download(tmp_path, monkeypatch):
    client = setup_client(tmp_path, monkeypatch)
    response = client.post("/api/v1/certificate-jobs", json={
        "organization": "Test Organization",
        "recipients": [
            {"name": "Asha Kumar", "email": "asha@example.com", "course": "Python Basics",
             "event_name": "Tech Day", "issue_date": "2026-10-07"},
            {"name": "", "email": "not-an-email", "course": "Python Basics",
             "event_name": "Tech Day", "issue_date": "2026-10-07"}
        ]
    })
    assert response.status_code == 202
    job_id = response.json()["job_id"]
    status = client.get(f"/api/v1/certificate-jobs/{job_id}")
    assert status.status_code == 200
    body = status.json()
    assert body["total"] == 2
    assert body["processed"] == 2
    assert body["succeeded"] == 1
    assert body["failed"] == 1
    assert body["status"] == "completed_with_errors"
    assert body["progress_percent"] == 100
    successful = next(r for r in body["recipients"] if r["status"] == "completed")
    pdf = client.get(f"/api/v1/certificate-jobs/{job_id}/certificates/{successful['id']}")
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF")
    archive = client.get(f"/api/v1/certificate-jobs/{job_id}/download")
    assert archive.status_code == 200
    assert archive.content[:2] == b"PK"


def test_empty_recipient_list_rejected(tmp_path, monkeypatch):
    client = setup_client(tmp_path, monkeypatch)
    response = client.post("/api/v1/certificate-jobs", json={"recipients": []})
    assert response.status_code == 422


def test_unknown_job_returns_404(tmp_path, monkeypatch):
    client = setup_client(tmp_path, monkeypatch)
    assert client.get("/api/v1/certificate-jobs/not-a-real-job").status_code == 404
