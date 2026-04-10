from functools import partial
from datetime import datetime, timezone

from aio_pika.exceptions import AMQPException
from fastapi import Depends, FastAPI, File, Form, HTTPException, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.db import Base, SessionLocal, engine, get_db
from app.knowledge_ingest_service import (
    get_pdf_upload_max_size_bytes,
    read_upload_file_with_limit,
    validate_pdf_upload_metadata,
)
from app.knowledge_queue import publish_pdf_ingest_job
from app.langchain_agent_service import (
    build_augmented_prompt,
    ensure_vector_store_schema,
    get_or_create_memory_snapshot,
    get_recent_chat_turns,
    ingest_knowledge_document,
    refresh_memory_summary_if_needed,
    retrieve_relevant_chunks,
    rewrite_query_for_retrieval,
)
from app.llm_service import invoke_deepseek_chat, stream_deepseek_chat
from app.models import Agent, ChatTurn, Execution, KnowledgeIngestJob, KnowledgeIngestPayload
from app.schemas import (
    AgentCreate,
    AgentOut,
    ChatStreamInput,
    ExecutionOut,
    KnowledgeDocumentCreate,
    KnowledgeDocumentOut,
    KnowledgeIngestJobOut,
    KnowledgePdfUploadOut,
    RunAgentInput,
)
from app.streaming_utils import create_streaming_response, stream_execution_chunks

app = FastAPI(title="My Agent Platform")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def build_basic_stream_output(full_message: str) -> dict:
    return {"message": full_message}


def build_chat_stream_output(full_message: str, references: list[dict]) -> dict:
    return {"message": full_message, "references": references}


def persist_assistant_chat_turn(full_message: str, db_session: Session, agent_id: str) -> None:
    assistant_turn = ChatTurn(agent_id=agent_id, role="assistant", content=full_message)
    db_session.add(assistant_turn)
    db_session.flush()


def refresh_memory_summary_safe(full_message: str, db_session: Session, agent_name: str, agent_id: str) -> None:
    del full_message
    try:
        refresh_memory_summary_if_needed(
            db_session=db_session,
            agent_name=agent_name,
            agent_id=agent_id,
        )
    except (RuntimeError, ValueError):
        db_session.rollback()


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    startup_db = SessionLocal()
    try:
        ensure_vector_store_schema(startup_db)
    finally:
        startup_db.close()


@app.get("/health")
def health():
    return {"status": "ok"}

##response_model参数会自动将返回的数据转换成指定的格式，这里是AgentOut类的格式
@app.post("/agents", response_model=AgentOut)
def create_agent(payload: AgentCreate, db: Session = Depends(get_db)):
    agent = Agent(name=payload.name, description=payload.description)
    ##将agent对象添加到数据库会话中，并提交事务。commit之后，数据库会生成id和created_at等字段的值
    db.add(agent)
    db.commit()
    ##refresh相当于回填的过程，将数据库中生成的id和created_at等字段回填到agent对象中
    db.refresh(agent)
    return agent


@app.get("/agents", response_model=list[AgentOut])
def list_agents(db: Session = Depends(get_db)):
    return db.query(Agent).order_by(Agent.created_at.desc()).all()


@app.get("/agents/{agent_id}/executions", response_model=list[ExecutionOut])
def list_agent_executions(agent_id: str, db: Session = Depends(get_db)):
    agent = db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    return (
        db.query(Execution)
        .filter(Execution.agent_id == agent_id)
        .order_by(Execution.created_at.asc())
        .all()
    )


@app.delete("/agents/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_agent(agent_id: str, db: Session = Depends(get_db)):
    agent = db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    db.query(Execution).filter(Execution.agent_id == agent_id).delete(synchronize_session=False)
    db.query(ChatTurn).filter(ChatTurn.agent_id == agent_id).delete(synchronize_session=False)
    db.query(KnowledgeIngestJob).filter(KnowledgeIngestJob.agent_id == agent_id).delete(
        synchronize_session=False
    )
    db.delete(agent)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post("/agents/{agent_id}/knowledge/documents", response_model=KnowledgeDocumentOut)
def add_knowledge_document(
    agent_id: str, payload: KnowledgeDocumentCreate, db: Session = Depends(get_db)
):
    agent = db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    try:
        document_id, chunk_count = ingest_knowledge_document(
            db_session=db,
            agent_id=agent_id,
            payload=payload,
        )
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return KnowledgeDocumentOut(document_id=document_id, chunk_count=chunk_count)


@app.post(
    "/agents/{agent_id}/knowledge/pdf",
    response_model=KnowledgePdfUploadOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def enqueue_pdf_knowledge_ingest(
    agent_id: str,
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    db: Session = Depends(get_db),
):
    agent = db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    normalized_file_name = validate_pdf_upload_metadata(file.filename, file.content_type)

    try:
        max_size_bytes = get_pdf_upload_max_size_bytes()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        payload_bytes = await read_upload_file_with_limit(file, max_size_bytes=max_size_bytes)
    finally:
        await file.close()

    ingest_job = KnowledgeIngestJob(
        agent_id=agent_id,
        source_type="pdf",
        file_name=normalized_file_name,
        file_size=len(payload_bytes),
        title=title.strip() if isinstance(title, str) and title.strip() else None,
        status="pending",
    )
    db.add(ingest_job)
    db.flush()

    db.add(KnowledgeIngestPayload(job_id=ingest_job.id, payload_bytes=payload_bytes))
    db.commit()
    db.refresh(ingest_job)

    try:
        await publish_pdf_ingest_job(ingest_job.id)
    except (AMQPException, OSError, RuntimeError, ValueError) as exc:
        payload = db.get(KnowledgeIngestPayload, ingest_job.id)
        ingest_job.status = "failed"
        ingest_job.error_message = f"Queue publish failed: {exc}"
        ingest_job.finished_at = datetime.now(timezone.utc)
        if payload is not None:
            db.delete(payload)
        db.commit()
        raise HTTPException(status_code=503, detail="Failed to enqueue knowledge ingest job.") from exc

    return KnowledgePdfUploadOut(job_id=ingest_job.id, status=ingest_job.status)


@app.get("/agents/{agent_id}/knowledge/jobs/{job_id}", response_model=KnowledgeIngestJobOut)
def get_knowledge_ingest_job(agent_id: str, job_id: str, db: Session = Depends(get_db)):
    ingest_job = db.get(KnowledgeIngestJob, job_id)
    if not ingest_job or ingest_job.agent_id != agent_id:
        raise HTTPException(status_code=404, detail="Knowledge ingest job not found")
    return ingest_job


@app.post("/agents/{agent_id}/run", response_model=ExecutionOut)
def run_agent(agent_id: str, payload: RunAgentInput, db: Session = Depends(get_db)):
    agent = db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    prompt_value = payload.input_data.get("prompt")
    if not isinstance(prompt_value, str) or not prompt_value.strip():
        raise HTTPException(status_code=400, detail="input_data.prompt must be a non-empty string")

    execution = Execution(
        agent_id=agent_id,
        status="running",
        input_data=payload.input_data,
        started_at=datetime.now(timezone.utc),
    )
    db.add(execution)
    db.commit()
    db.refresh(execution)

    try:
        assistant_message = invoke_deepseek_chat(agent_name=agent.name, user_prompt=prompt_value)
        result = {"message": assistant_message}
        execution.status = "success"
        execution.output_data = result
        execution.finished_at = datetime.now(timezone.utc)
    except (RuntimeError, ValueError) as exc:
        execution.status = "failed"
        execution.error = str(exc)
        execution.finished_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(execution)
    return execution


@app.post("/agents/{agent_id}/run/stream")
def run_agent_stream(agent_id: str, payload: RunAgentInput, db: Session = Depends(get_db)):
    agent = db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    prompt_value = payload.input_data.get("prompt")
    if not isinstance(prompt_value, str) or not prompt_value.strip():
        raise HTTPException(status_code=400, detail="input_data.prompt must be a non-empty string")

    execution = Execution(
        agent_id=agent_id,
        status="running",
        input_data=payload.input_data,
        started_at=datetime.now(timezone.utc),
    )
    db.add(execution)
    db.commit()
    db.refresh(execution)

    stream_iterator = stream_execution_chunks(
        db_session=db,
        execution=execution,
        chunk_iterator=stream_deepseek_chat(agent_name=agent.name, user_prompt=prompt_value),
        on_success_output=build_basic_stream_output,
    )
    return create_streaming_response(stream_iterator)


@app.post("/agents/{agent_id}/chat/stream")
def chat_with_memory_and_retrieval(
    agent_id: str, payload: ChatStreamInput, db: Session = Depends(get_db)
):
    agent = db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    user_message = payload.message.strip()
    if not user_message:
        raise HTTPException(status_code=400, detail="message must be a non-empty string")

    execution = Execution(
        agent_id=agent_id,
        status="running",
        input_data={"prompt": user_message, "mode": "langchain"},
        started_at=datetime.now(timezone.utc),
    )
    db.add(execution)
    db.flush()

    user_turn = ChatTurn(agent_id=agent_id, role="user", content=user_message)
    db.add(user_turn)
    db.flush()

    memory_snapshot = get_or_create_memory_snapshot(db_session=db, agent_id=agent_id)
    recent_turns = get_recent_chat_turns(db_session=db, agent_id=agent_id, limit=10)

    try:
        rewritten_query = rewrite_query_for_retrieval(
            agent_name=agent.name,
            user_message=user_message,
            memory_summary=memory_snapshot.summary_text,
            recent_turns=recent_turns,
        )
        retrieved_chunks = retrieve_relevant_chunks(
            db_session=db,
            agent_id=agent_id,
            query_text=rewritten_query,
            top_k=payload.top_k,
        )
        augmented_prompt = build_augmented_prompt(
            agent_name=agent.name,
            user_message=user_message,
            memory_summary=memory_snapshot.summary_text,
            recent_turns=recent_turns,
            retrieved_chunks=retrieved_chunks,
        )
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    db.commit()
    db.refresh(execution)

    references = [
        {
            "chunk_id": chunk.chunk_id,
            "score": round(chunk.score, 4),
            "content_preview": chunk.content[:180],
            "file_name": chunk.metadata.get("file_name"),
            "page": chunk.metadata.get("page"),
            "metadata": chunk.metadata,
        }
        for chunk in retrieved_chunks
    ]

    stream_iterator = stream_execution_chunks(
        db_session=db,
        execution=execution,
        chunk_iterator=stream_deepseek_chat(agent_name=agent.name, user_prompt=augmented_prompt),
        on_success_output=partial(build_chat_stream_output, references=references),
        on_success_before_commit=partial(persist_assistant_chat_turn, db_session=db, agent_id=agent_id),
        on_success_after_commit=partial(
            refresh_memory_summary_safe,
            db_session=db,
            agent_name=agent.name,
            agent_id=agent_id,
        ),
    )
    return create_streaming_response(stream_iterator)


@app.get("/executions/{execution_id}", response_model=ExecutionOut)
def get_execution(execution_id: str, db: Session = Depends(get_db)):
    execution = db.get(Execution, execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")
    return execution
