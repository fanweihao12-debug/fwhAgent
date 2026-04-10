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

export interface MessageItem {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  createdAt: string;
  status?: 'pending' | 'typing' | 'done' | 'error';
}
