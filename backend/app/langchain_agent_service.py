import json
import os
import uuid
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from langchain_core.prompts import ChatPromptTemplate
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.llm_service import invoke_deepseek_chat
from app.models import AgentMemorySnapshot, ChatTurn, KnowledgeDocument
from app.schemas import KnowledgeDocumentCreate

DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_LOCAL_EMBEDDING_MODEL = "BAAI/bge-small-zh-v1.5"
_LOCAL_EMBEDDER: Any | None = None


@dataclass
class RetrievedChunk:
    chunk_id: str
    content: str
    score: float
    metadata: dict[str, Any]


def get_embedding_dimension() -> int:
    """Return configured embedding vector dimension for pgvector table."""
    configured_dimension = os.getenv("EMBEDDING_DIMENSION")
    if configured_dimension:
        return int(configured_dimension)

    provider = os.getenv("EMBEDDING_PROVIDER", "local").lower()
    if provider == "local":
        return 512
    return 1536


def ensure_vector_store_schema(db_session: Session) -> None:
    """Create pgvector extension and chunk table used by retrieval."""
    embedding_dimension = get_embedding_dimension()
    db_session.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
    db_session.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS knowledge_chunks (
                id VARCHAR(36) PRIMARY KEY,
                agent_id VARCHAR(36) NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
                document_id VARCHAR(36) NOT NULL REFERENCES knowledge_documents(id) ON DELETE CASCADE,
                chunk_index INTEGER NOT NULL,
                content TEXT NOT NULL,
                metadata_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                embedding vector({embedding_dimension}) NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )
    )
    try:
        db_session.execute(
            text(
                f"ALTER TABLE knowledge_chunks ALTER COLUMN embedding TYPE vector({embedding_dimension});"
            )
        )
    except Exception as exc:
        db_session.rollback()
        raise RuntimeError(
            "knowledge_chunks.embedding dimension is incompatible with EMBEDDING_DIMENSION. "
            "Please align EMBEDDING_DIMENSION with your embedding model or recreate the table."
        ) from exc

    db_session.execute(
        text("CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_agent_id ON knowledge_chunks(agent_id);")
    )
    db_session.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_embedding
            ON knowledge_chunks USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = 100);
            """
        )
    )
    db_session.commit()


def embedding_to_vector_literal(embedding: list[float]) -> str:
    """Serialize embedding values to pgvector literal format."""
    expected_dimension = get_embedding_dimension()
    if len(embedding) != expected_dimension:
        raise ValueError(
            f"Embedding dimension mismatch: expected {expected_dimension}, got {len(embedding)}."
        )
    return "[" + ",".join(f"{value:.8f}" for value in embedding) + "]"


def create_text_embedding(text_value: str) -> list[float]:
    """Create text embedding by calling an OpenAI-compatible embeddings endpoint."""
    provider = os.getenv("EMBEDDING_PROVIDER", "local").lower()
    if provider == "local":
        return create_local_text_embedding(text_value=text_value)
    return create_remote_text_embedding(text_value=text_value)


def create_local_text_embedding(text_value: str) -> list[float]:
    """Create embedding locally with sentence-transformers model."""
    global _LOCAL_EMBEDDER

    model_name = os.getenv("LOCAL_EMBEDDING_MODEL", DEFAULT_LOCAL_EMBEDDING_MODEL)
    if _LOCAL_EMBEDDER is None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "sentence-transformers is not installed. "
                "Install it or switch EMBEDDING_PROVIDER to openai_compatible."
            ) from exc
        _LOCAL_EMBEDDER = SentenceTransformer(model_name)

    embedding_array = _LOCAL_EMBEDDER.encode(text_value, normalize_embeddings=True)
    embedding = embedding_array.tolist() if hasattr(embedding_array, "tolist") else list(embedding_array)
    return [float(item) for item in embedding]


def create_remote_text_embedding(text_value: str) -> list[float]:
    """Create embedding by calling an OpenAI-compatible embeddings endpoint."""
    api_key = os.getenv("EMBEDDING_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise ValueError("EMBEDDING_API_KEY (or DEEPSEEK_API_KEY) is not set.")

    embedding_base_url = (
        os.getenv("EMBEDDING_BASE_URL")
        or os.getenv("DEEPSEEK_BASE_URL")
        or "https://api.deepseek.com"
    ).rstrip("/")
    embedding_model = os.getenv("EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)
    timeout_seconds = float(os.getenv("DEEPSEEK_TIMEOUT_SECONDS", "60"))

    payload = {"model": embedding_model, "input": text_value}
    request = Request(
        url=f"{embedding_base_url}/embeddings",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            raw_body = response.read().decode("utf-8")
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Embedding HTTP error {exc.code}: {error_body}") from exc
    except URLError as exc:
        raise RuntimeError(f"Embedding network error: {exc.reason}") from exc
    except TimeoutError as exc:
        raise RuntimeError("Embedding request timed out.") from exc

    payload_data = json.loads(raw_body)
    data_items = payload_data.get("data")
    if not isinstance(data_items, list) or len(data_items) == 0:
        raise ValueError("Embedding response does not contain data.")

    first_item = data_items[0]
    if not isinstance(first_item, dict):
        raise ValueError("Embedding response item format is invalid.")

    embedding = first_item.get("embedding")
    if not isinstance(embedding, list) or not all(isinstance(item, (float, int)) for item in embedding):
        raise ValueError("Embedding vector is missing or invalid.")

    return [float(item) for item in embedding]


def ingest_knowledge_document(
    db_session: Session, agent_id: str, payload: KnowledgeDocumentCreate
) -> tuple[str, int]:
    """Split document content, embed chunks, and persist them into pgvector table."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=int(os.getenv("RAG_CHUNK_SIZE", "900")),
        chunk_overlap=int(os.getenv("RAG_CHUNK_OVERLAP", "120")),
    )
    chunks = splitter.split_text(payload.content)
    if len(chunks) == 0:
        raise ValueError("Document content cannot be split into chunks.")

    document = KnowledgeDocument(
        agent_id=agent_id,
        title=payload.title,
        source=payload.source,
        metadata_json=payload.metadata,
    )
    db_session.add(document)
    db_session.flush()

    for chunk_index, chunk_text in enumerate(chunks):
        embedding = create_text_embedding(chunk_text)
        metadata = {
            "title": payload.title,
            "source": payload.source,
            "chunk_index": chunk_index,
            **payload.metadata,
        }
        db_session.execute(
            text(
                """
                INSERT INTO knowledge_chunks (
                    id, agent_id, document_id, chunk_index, content, metadata_json, embedding
                ) VALUES (
                    :id, :agent_id, :document_id, :chunk_index, :content, CAST(:metadata_json AS jsonb), CAST(:embedding AS vector)
                );
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "agent_id": agent_id,
                "document_id": document.id,
                "chunk_index": chunk_index,
                "content": chunk_text,
                "metadata_json": json.dumps(metadata, ensure_ascii=False),
                "embedding": embedding_to_vector_literal(embedding),
            },
        )

    db_session.commit()
    return document.id, len(chunks)


def get_recent_chat_turns(db_session: Session, agent_id: str, limit: int) -> list[ChatTurn]:
    """Fetch recent chat turns in chronological order for context window."""
    latest_turns = (
        db_session.query(ChatTurn)
        .filter(ChatTurn.agent_id == agent_id)
        .order_by(ChatTurn.created_at.desc())
        .limit(limit)
        .all()
    )
    return list(reversed(latest_turns))


def get_or_create_memory_snapshot(db_session: Session, agent_id: str) -> AgentMemorySnapshot:
    """Load memory snapshot row, creating an empty snapshot when missing."""
    snapshot = db_session.get(AgentMemorySnapshot, agent_id)
    if snapshot is not None:
        return snapshot

    snapshot = AgentMemorySnapshot(agent_id=agent_id, summary_text="")
    db_session.add(snapshot)
    db_session.flush()
    return snapshot


def retrieve_relevant_chunks(
    db_session: Session, agent_id: str, query_text: str, top_k: int
) -> list[RetrievedChunk]:
    """Retrieve nearest chunks from pgvector by cosine distance."""
    query_embedding = create_text_embedding(query_text)
    result_rows = db_session.execute(
        text(
            """
            SELECT id, content, metadata_json, 1 - (embedding <=> CAST(:query_embedding AS vector)) AS score
            FROM knowledge_chunks
            WHERE agent_id = :agent_id
            ORDER BY embedding <=> CAST(:query_embedding AS vector)
            LIMIT :top_k;
            """
        ),
        {
            "agent_id": agent_id,
            "query_embedding": embedding_to_vector_literal(query_embedding),
            "top_k": top_k,
        },
    ).mappings()

    chunks: list[RetrievedChunk] = []
    for row in result_rows:
        metadata_value = row["metadata_json"]
        metadata = metadata_value if isinstance(metadata_value, dict) else {}
        chunks.append(
            RetrievedChunk(
                chunk_id=row["id"],
                content=row["content"],
                score=float(row["score"]) if row["score"] is not None else 0.0,
                metadata=metadata,
            )
        )
    return chunks


def rewrite_query_for_retrieval(
    agent_name: str, user_message: str, memory_summary: str, recent_turns: list[ChatTurn]
) -> str:
    """Use LLM to rewrite user question into a retrieval-friendly standalone query."""
    history_text = "\n".join(f"{turn.role}: {turn.content}" for turn in recent_turns[-6:])
    rewrite_prompt_template = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "Rewrite user question into a concise retrieval query. Return only one line query.",
            ),
            (
                "human",
                "Memory summary:\n{memory_summary}\n\nRecent turns:\n{history_text}\n\nOriginal question:\n{question}",
            ),
        ]
    )
    rendered_prompt = rewrite_prompt_template.format_messages(
        memory_summary=memory_summary or "(empty)",
        history_text=history_text or "(empty)",
        question=user_message,
    )
    prompt_text = "\n\n".join(
        f"[{message.type}] {message.content}" for message in rendered_prompt if isinstance(message.content, str)
    )
    rewritten_query = invoke_deepseek_chat(agent_name=agent_name, user_prompt=prompt_text).strip()
    return rewritten_query or user_message


def build_augmented_prompt(
    agent_name: str,
    user_message: str,
    memory_summary: str,
    recent_turns: list[ChatTurn],
    retrieved_chunks: list[RetrievedChunk],
) -> str:
    """Build final prompt that merges memory context and retrieval references."""
    history_text = "\n".join(f"{turn.role}: {turn.content}" for turn in recent_turns)
    references_text = "\n\n".join(
        f"[ref-{index + 1} | score={chunk.score:.3f}]\n{chunk.content}"
        for index, chunk in enumerate(retrieved_chunks)
    )

    answer_prompt_template = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are a helpful AI agent. Use references when relevant and answer in markdown.",
            ),
            (
                "human",
                "Agent name: {agent_name}\n\nMemory summary:\n{memory_summary}\n\nRecent turns:\n{history_text}\n\nRetrieved references:\n{references_text}\n\nUser question:\n{question}",
            ),
        ]
    )
    rendered_prompt = answer_prompt_template.format_messages(
        agent_name=agent_name,
        memory_summary=memory_summary or "(empty)",
        history_text=history_text or "(empty)",
        references_text=references_text or "(no references)",
        question=user_message,
    )
    return "\n\n".join(
        f"[{message.type}] {message.content}" for message in rendered_prompt if isinstance(message.content, str)
    )


def refresh_memory_summary_if_needed(db_session: Session, agent_name: str, agent_id: str) -> None:
    """Summarize old turns into snapshot once dialogue length exceeds threshold."""
    summarize_threshold = int(os.getenv("MEMORY_SUMMARIZE_THRESHOLD", "24"))
    keep_recent_turns = int(os.getenv("MEMORY_KEEP_RECENT_TURNS", "10"))

    total_turns = db_session.query(ChatTurn).filter(ChatTurn.agent_id == agent_id).count()
    if total_turns < summarize_threshold:
        return

    snapshot = get_or_create_memory_snapshot(db_session=db_session, agent_id=agent_id)
    older_turns = (
        db_session.query(ChatTurn)
        .filter(ChatTurn.agent_id == agent_id)
        .order_by(ChatTurn.created_at.asc())
        .limit(max(total_turns - keep_recent_turns, 0))
        .all()
    )
    if len(older_turns) == 0:
        return

    history_text = "\n".join(f"{turn.role}: {turn.content}" for turn in older_turns)
    summary_prompt_template = ChatPromptTemplate.from_messages(
        [
            ("system", "Summarize conversation memory for future turns in concise bullet points."),
            (
                "human",
                "Existing summary:\n{existing_summary}\n\nNew turns to fold in:\n{history_text}",
            ),
        ]
    )
    rendered_prompt = summary_prompt_template.format_messages(
        existing_summary=snapshot.summary_text or "(empty)",
        history_text=history_text,
    )
    summary_prompt = "\n\n".join(
        f"[{message.type}] {message.content}" for message in rendered_prompt if isinstance(message.content, str)
    )
    snapshot.summary_text = invoke_deepseek_chat(agent_name=agent_name, user_prompt=summary_prompt)
    db_session.commit()
