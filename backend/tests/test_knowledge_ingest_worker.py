import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db import SessionLocal
from app.knowledge_ingest_worker import decode_job_id, process_pdf_ingest_job
from app.models import Agent, KnowledgeIngestJob, KnowledgeIngestPayload


def _database_available() -> bool:
    db_session = SessionLocal()
    try:
        db_session.execute(text("SELECT 1"))
        return True
    except (OSError, RuntimeError, SQLAlchemyError):
        return False
    finally:
        db_session.close()


def _create_agent_and_job() -> tuple[str, str]:
    db_session = SessionLocal()
    try:
        agent = Agent(name=f"worker-test-{uuid.uuid4()}", description=None)
        db_session.add(agent)
        db_session.flush()

        job = KnowledgeIngestJob(
            agent_id=agent.id,
            source_type="pdf",
            file_name="manual.pdf",
            file_size=32,
            title="manual",
            status="pending",
        )
        db_session.add(job)
        db_session.flush()
        db_session.add(KnowledgeIngestPayload(job_id=job.id, payload_bytes=b"dummy-pdf"))
        db_session.commit()
        return agent.id, job.id
    finally:
        db_session.close()


def _cleanup_agent(agent_id: str) -> None:
    db_session = SessionLocal()
    try:
        db_session.query(KnowledgeIngestPayload).filter(KnowledgeIngestPayload.job_id.in_(
            db_session.query(KnowledgeIngestJob.id).filter(KnowledgeIngestJob.agent_id == agent_id)
        )).delete(synchronize_session=False)
        db_session.query(KnowledgeIngestJob).filter(KnowledgeIngestJob.agent_id == agent_id).delete(
            synchronize_session=False
        )
        agent = db_session.get(Agent, agent_id)
        if agent is not None:
            db_session.delete(agent)
        db_session.commit()
    finally:
        db_session.close()


def test_decode_job_id_rejects_invalid_payload() -> None:
    with pytest.raises(ValueError):
        decode_job_id(b"not-json")


def test_process_pdf_ingest_job_marks_success_and_deletes_payload(monkeypatch) -> None:
    if not _database_available():
        pytest.skip("database unavailable")

    agent_id, job_id = _create_agent_and_job()

    def fake_ingest_pdf_document(**kwargs) -> tuple[str, int]:
        del kwargs
        return "doc-id", 6

    monkeypatch.setattr("app.knowledge_ingest_worker.ingest_pdf_document", fake_ingest_pdf_document)

    try:
        process_pdf_ingest_job(job_id)
        db_session = SessionLocal()
        try:
            job = db_session.get(KnowledgeIngestJob, job_id)
            payload = db_session.get(KnowledgeIngestPayload, job_id)
            assert job is not None
            assert job.status == "success"
            assert job.chunk_count == 6
            assert payload is None
        finally:
            db_session.close()
    finally:
        _cleanup_agent(agent_id)


def test_process_pdf_ingest_job_marks_failed_and_deletes_payload(monkeypatch) -> None:
    if not _database_available():
        pytest.skip("database unavailable")

    agent_id, job_id = _create_agent_and_job()

    def fake_ingest_pdf_document(**kwargs) -> tuple[str, int]:
        del kwargs
        raise ValueError("corrupted pdf")

    monkeypatch.setattr("app.knowledge_ingest_worker.ingest_pdf_document", fake_ingest_pdf_document)

    try:
        process_pdf_ingest_job(job_id)
        db_session = SessionLocal()
        try:
            job = db_session.get(KnowledgeIngestJob, job_id)
            payload = db_session.get(KnowledgeIngestPayload, job_id)
            assert job is not None
            assert job.status == "failed"
            assert job.error_message is not None
            assert "corrupted pdf" in job.error_message
            assert payload is None
        finally:
            db_session.close()
    finally:
        _cleanup_agent(agent_id)
