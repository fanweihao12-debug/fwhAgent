export interface Agent {
  id: string;
  name: string;
  description: string | null;
  created_at: string;
}

export interface ExecutionResult {
  id: string;
  agent_id: string;
  status: 'running' | 'success' | 'failed';
  input_data: Record<string, unknown>;
  output_data: Record<string, unknown> | null;
  error: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface KnowledgePdfUploadResult {
  job_id: string;
  status: 'pending' | 'running' | 'success' | 'failed';
}

export interface KnowledgeIngestJob {
  id: string;
  agent_id: string;
  source_type: string;
  file_name: string;
  file_size: number;
  title: string | null;
  status: 'pending' | 'running' | 'success' | 'failed';
  chunk_count: number | null;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface MessageItem {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  createdAt: string;
  status?: 'pending' | 'typing' | 'done' | 'error';
}
