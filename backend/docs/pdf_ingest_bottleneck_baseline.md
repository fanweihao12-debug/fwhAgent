# PDF Ingest Bottleneck Baseline (Current State)

## Scope
- Baseline target: current synchronous path in `ingest_knowledge_document`.
- File: `backend/app/langchain_agent_service.py`.

## Current Flow
1. Split full text into chunks with `RecursiveCharacterTextSplitter`.
2. Loop chunks one by one:
3. Generate embedding for each chunk (`create_text_embedding`).
4. Insert each chunk row into `knowledge_chunks`.
5. Commit transaction at the end.

## Confirmed Bottlenecks
- **Synchronous request path**: ingest runs in API request lifecycle, so large PDF blocks request thread.
- **Per-chunk embedding calls**: one embedding call per chunk in a tight loop; latency grows linearly with chunk count.
- **No job queue**: no decoupling between upload and vectorization, no retry/status model.

## Why This Matters
- A 100+ chunk PDF can cause long request latency and timeout risk.
- User cannot get immediate upload feedback other than waiting for full ingest completion.

## Next Steps Applied in This Change
- Add async ingest job model (`knowledge_ingest_jobs`) for queue semantics.
- Add payload staging model (`knowledge_ingest_payloads`) for non-file persistence.
- Add upload and job status APIs to support async processing pipeline.
