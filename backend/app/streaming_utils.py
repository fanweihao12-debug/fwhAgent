import json
from datetime import datetime, timezone
from typing import Any, Callable, Iterator

from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.models import Execution


def to_sse(event: str, data: dict[str, Any]) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


def create_streaming_response(stream_iterator: Iterator[str]) -> StreamingResponse:
    return StreamingResponse(
        stream_iterator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def stream_execution_chunks(
    db_session: Session,
    execution: Execution,
    chunk_iterator: Iterator[str],
    on_success_output: Callable[[str], dict[str, Any]],
    on_success_before_commit: Callable[[str], None] | None = None,
    on_success_after_commit: Callable[[str], None] | None = None,
) -> Iterator[str]:
    assistant_chunks: list[str] = []
    try:
        for chunk in chunk_iterator:
            assistant_chunks.append(chunk)
            yield to_sse("delta", {"content": chunk, "execution_id": execution.id})

        full_message = "".join(assistant_chunks)
        if on_success_before_commit is not None:
            on_success_before_commit(full_message)

        output_payload = on_success_output(full_message)
        execution.status = "success"
        execution.output_data = output_payload
        execution.finished_at = datetime.now(timezone.utc)
        db_session.commit()
        db_session.refresh(execution)

        if on_success_after_commit is not None:
            on_success_after_commit(full_message)

        done_payload: dict[str, Any] = {"execution_id": execution.id}
        references = output_payload.get("references")
        if isinstance(references, list):
            done_payload["references"] = references
        yield to_sse("done", done_payload)
    except (RuntimeError, ValueError) as exc:
        execution.status = "failed"
        execution.error = str(exc)
        execution.finished_at = datetime.now(timezone.utc)
        db_session.commit()
        db_session.refresh(execution)
        yield to_sse("error", {"execution_id": execution.id, "message": str(exc)})
