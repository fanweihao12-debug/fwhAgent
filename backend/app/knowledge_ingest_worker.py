import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

import aio_pika
from aio_pika.abc import AbstractIncomingMessage
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.knowledge_queue import get_knowledge_ingest_queue_name, get_rabbitmq_url
from app.langchain_agent_service import ensure_vector_store_schema, ingest_pdf_document
from app.models import KnowledgeIngestJob, KnowledgeIngestPayload

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def decode_job_id(message_body: bytes) -> str:
    """Parse queue message and return the job id."""
    try:
        payload = json.loads(message_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid queue message payload.") from exc

    if not isinstance(payload, dict):
        raise ValueError("Queue message payload must be a JSON object.")

    raw_job_id = payload.get("job_id")
    if not isinstance(raw_job_id, str) or len(raw_job_id.strip()) == 0:
        raise ValueError("Queue message must contain a non-empty job_id.")

    return raw_job_id.strip()


def _finalize_failed_job(
    db_session: Session,
    job_id: str,
    error_message: str,
) -> None:
    job = db_session.get(KnowledgeIngestJob, job_id)
    if job is None:
        return

    payload = db_session.get(KnowledgeIngestPayload, job_id)
    job.status = "failed"
    job.error_message = error_message
    job.finished_at = _utc_now()
    if payload is not None:
        db_session.delete(payload)
    db_session.commit()


def process_pdf_ingest_job(job_id: str) -> None:
    """Consume one PDF ingest job: parse PDF, split, embed, and persist chunks."""
    db_session = SessionLocal()
    try:
        job = db_session.get(KnowledgeIngestJob, job_id)
        if job is None:
            return

        payload = db_session.get(KnowledgeIngestPayload, job_id)
        if payload is None:
            _finalize_failed_job(db_session, job_id, "Knowledge ingest payload not found.")
            return

        job.status = "running"
        job.started_at = _utc_now()
        job.error_message = None
        job.finished_at = None
        db_session.commit()
        db_session.refresh(job)

        try:
            _, chunk_count = ingest_pdf_document(
                db_session=db_session,
                agent_id=job.agent_id,
                file_name=job.file_name,
                pdf_bytes=payload.payload_bytes,
                title=job.title,
                commit=False,
            )
            job.status = "success"
            job.chunk_count = chunk_count
            job.error_message = None
            job.finished_at = _utc_now()
            db_session.delete(payload)
            db_session.commit()
        except (RuntimeError, ValueError, OSError) as exc:
            db_session.rollback()
            _finalize_failed_job(db_session, job_id, str(exc))
    finally:
        db_session.close()


async def handle_pdf_ingest_message(message: AbstractIncomingMessage) -> None:
    """Handle one RabbitMQ message for PDF ingest."""
    async with message.process(requeue=False):
        try:
            job_id = decode_job_id(message.body)
        except ValueError as exc:
            logger.error("Discard invalid ingest queue message: %s", exc)
            return

        process_pdf_ingest_job(job_id)


def ensure_worker_schema() -> None:
    """Ensure vector schema exists before worker consumes jobs."""
    db_session = SessionLocal()
    try:
        ensure_vector_store_schema(db_session)
    finally:
        db_session.close()


async def run_worker() -> None:
    """Run RabbitMQ consumer for PDF ingest jobs."""
    ensure_worker_schema()

    connection = await aio_pika.connect_robust(get_rabbitmq_url())
    channel = await connection.channel()
    await channel.set_qos(prefetch_count=1)
    queue = await channel.declare_queue(get_knowledge_ingest_queue_name(), durable=True)
    await queue.consume(handle_pdf_ingest_message)

    logger.info("PDF ingest worker started, queue=%s", queue.name)
    await asyncio.Future()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_worker())
