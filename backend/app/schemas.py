"""
定义了FastAPI应用中使用的Pydantic模型，用于数据验证和序列化。"""
from datetime import datetime

from pydantic import BaseModel, Field


class AgentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None


class AgentOut(BaseModel):
    id: str
    name: str
    description: str | None
    created_at: datetime

    class Config:
        from_attributes = True


class RunAgentInput(BaseModel):
    input_data: dict = Field(default_factory=dict)


class ExecutionOut(BaseModel):
    id: str
    agent_id: str
    status: str
    input_data: dict
    output_data: dict | None
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    class Config:
        from_attributes = True


class KnowledgeDocumentCreate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    source: str | None = Field(default=None, max_length=500)
    content: str = Field(min_length=1)
    metadata: dict = Field(default_factory=dict)


class KnowledgeDocumentOut(BaseModel):
    document_id: str
    chunk_count: int


class ChatStreamInput(BaseModel):
    message: str = Field(min_length=1)
    top_k: int = Field(default=4, ge=1, le=12)
