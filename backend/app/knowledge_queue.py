import json
import os

import aio_pika
from aio_pika import DeliveryMode, Message

DEFAULT_RABBITMQ_URL = "amqp://guest:guest@127.0.0.1:5672/"
DEFAULT_KNOWLEDGE_INGEST_QUEUE = "knowledge_pdf_ingest"


def get_rabbitmq_url() -> str:
    """Return RabbitMQ connection URL used by API and worker."""
    configured_url = os.getenv("RABBITMQ_URL", DEFAULT_RABBITMQ_URL).strip()
    if len(configured_url) == 0:
        raise ValueError("RABBITMQ_URL must not be empty.")
    return configured_url


def get_knowledge_ingest_queue_name() -> str:
    """Return queue name used for PDF ingest jobs."""
    configured_name = os.getenv("KNOWLEDGE_INGEST_QUEUE", DEFAULT_KNOWLEDGE_INGEST_QUEUE).strip()
    if len(configured_name) == 0:
        raise ValueError("KNOWLEDGE_INGEST_QUEUE must not be empty.")
    return configured_name


async def publish_pdf_ingest_job(job_id: str) -> None:
    """Publish a PDF ingest job message to RabbitMQ."""
    rabbitmq_url = get_rabbitmq_url()
    queue_name = get_knowledge_ingest_queue_name()
    message_body = json.dumps({"job_id": job_id}, ensure_ascii=False).encode("utf-8")

    connection = await aio_pika.connect_robust(rabbitmq_url)
    async with connection:
        channel = await connection.channel(publisher_confirms=True)
        await channel.declare_queue(queue_name, durable=True)
        await channel.default_exchange.publish(
            Message(
                body=message_body,
                delivery_mode=DeliveryMode.PERSISTENT,
                content_type="application/json",
            ),
            routing_key=queue_name,
        )
