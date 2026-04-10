# FWH Agent Platform

一个基于 **FastAPI + React + PostgreSQL(pgvector)** 的 Agent 平台示例项目，支持：

- Agent 创建与管理
- 同步 / 流式聊天
- Markdown 实时渲染
- 基于 LangChain 思路的上下文记忆与向量检索（RAG）
- 对话与执行记录持久化

## 1. 项目功能

### 1.1 Agent 基础能力

- 创建 Agent
- 查看 Agent 列表
- 删除 Agent（包含关联聊天与执行记录）

### 1.2 聊天能力

- 普通流式聊天：`/agents/{agent_id}/run/stream`
- 增强流式聊天（记忆 + 检索）：`/agents/{agent_id}/chat/stream`
- 前端逐字显示（打字机效果）
- Assistant 消息 Markdown 渲染

### 1.3 记忆与检索（RAG）

- 文档入库并切分 chunk
- 本地向量生成（`sentence-transformers`）
- pgvector 相似度检索
- Query 重写（提高检索命中）
- 历史摘要（memory snapshot）+ 最近窗口上下文

## 2. 技术栈

### Backend

- Python 3.12+
- FastAPI
- SQLAlchemy
- PostgreSQL + pgvector
- LangChain / langchain-core / langchain-text-splitters
- sentence-transformers

### Frontend

- React 18 + TypeScript + Vite
- TanStack Query
- Zustand
- react-markdown + remark-gfm

### Infra

- Docker Compose
- PostgreSQL（`pgvector/pgvector:pg16`）
- Redis
- RabbitMQ

## 3. 目录结构

```text
fwhAgent/
  ├─ backend/
  │  ├─ app/
  │  │  ├─ main.py                     # FastAPI 路由入口
  │  │  ├─ models.py                   # SQLAlchemy 模型
  │  │  ├─ schemas.py                  # Pydantic schema
  │  │  ├─ db.py                       # DB 连接与会话
  │  │  ├─ llm_service.py              # DeepSeek 调用
  │  │  ├─ langchain_agent_service.py  # 记忆/检索服务
  │  │  └─ streaming_utils.py          # SSE 流式工具
  │  └─ tests/
  ├─ frontend/
  │  ├─ src/
  │  │  ├─ api/
  │  │  ├─ components/
  │  │  ├─ pages/
  │  │  └─ stores/
  └─ infra/
     ├─ docker-compose.yml
     └─ postgres-init/01-enable-pgvector.sql
```

## 4. 快速启动

## 4.1 启动基础依赖（DB/Redis/RabbitMQ）

在 `infra/` 下执行：

```bash
docker compose up -d
```

## 4.2 配置后端环境变量

编辑 `backend/.env`（至少配置 DeepSeek Key）：

```env
DATABASE_URL=postgresql+psycopg2://agent:agent@127.0.0.1:5432/agent

DEEPSEEK_API_KEY=your_deepseek_key
DEEPSEEK_MODEL=deepseek-chat
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_TIMEOUT_SECONDS=60

# 向量配置（默认本地 embedding）
EMBEDDING_PROVIDER=local
LOCAL_EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5
EMBEDDING_DIMENSION=512
```

说明：

- `EMBEDDING_PROVIDER=local` 时，不走 OpenAI embeddings API。
- 如需远程 OpenAI 兼容 embeddings，可切到 `openai_compatible` 并配置 `EMBEDDING_API_KEY` / `EMBEDDING_BASE_URL`。

## 4.3 启动后端

在 `backend/` 下执行（示例）：

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## 4.4 启动前端

在 `frontend/` 下执行：

```bash
npm install
npm run dev
```

访问：

- Frontend: `http://127.0.0.1:5173`
- Backend OpenAPI: `http://127.0.0.1:8000/docs`

## 5. 主要接口

### Agent 与执行

- `POST /agents` 创建 Agent
- `GET /agents` 获取 Agent 列表
- `DELETE /agents/{agent_id}` 删除 Agent 及关联数据
- `POST /agents/{agent_id}/run` 同步调用
- `POST /agents/{agent_id}/run/stream` 基础流式调用
- `GET /agents/{agent_id}/executions` 获取执行历史

### RAG 增强接口（新增）

- `POST /agents/{agent_id}/knowledge/documents`
  - 入参：`title/source/content/metadata`
  - 功能：文档切分 + embedding + 向量入库

- `POST /agents/{agent_id}/chat/stream`
  - 入参：`message`, `top_k`
  - 功能：记忆 + 检索 + 流式回答
  - SSE 事件：
    - `delta`: 增量文本
    - `done`: 结束（含 references）
    - `error`: 错误

## 6. 记忆与检索流程（当前实现）

1. 保存用户消息为 `chat_turns`
2. 读取 memory snapshot + 最近 N 轮对话
3. 用 LLM 改写检索 query
4. 在 `knowledge_chunks` 中做向量检索
5. 组装增强提示词
6. DeepSeek 流式生成并推送 SSE
7. 保存 assistant 回答与引用信息
8. 达到阈值后更新 memory summary

## 7. 常见问题

- `pgvector` 不可用：
  - 确认使用镜像 `pgvector/pgvector:pg16`
  - 确认扩展已安装：`CREATE EXTENSION IF NOT EXISTS vector;`

- embedding 维度不匹配：
  - 检查 `EMBEDDING_DIMENSION` 与模型输出维度是否一致
  - 本项目默认本地模型为 512 维

## 8. 分支约定

- `main`: 稳定分支
- `develop`: 日常开发分支
