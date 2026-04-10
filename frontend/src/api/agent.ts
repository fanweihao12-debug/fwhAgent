import { API_BASE_URL, requestJson } from './client';
import type { Agent, ExecutionResult } from '../types/agent';

interface CreateAgentPayload {
  name: string;
  description?: string | null;
}

interface RunAgentPayload {
  input_data: Record<string, unknown>;
}

interface StreamCallbacks {
  onDelta: (chunk: string) => void;
  onDone?: () => void;
}

interface ChatStreamPayload {
  message: string;
  top_k?: number;
}

interface KnowledgeDocumentPayload {
  title?: string | null;
  source?: string | null;
  content: string;
  metadata?: Record<string, unknown>;
}

interface KnowledgeDocumentResult {
  document_id: string;
  chunk_count: number;
}

export const fetchAgentList = async (): Promise<Agent[]> => requestJson<Agent[]>('/agents');

export const createAgent = async (payload: CreateAgentPayload): Promise<Agent> =>
  requestJson<Agent>('/agents', {
    method: 'POST',
    bodyJson: payload
  });

export const runAgent = async (agentId: string, payload: RunAgentPayload): Promise<ExecutionResult> =>
  requestJson<ExecutionResult>(`/agents/${agentId}/run`, {
    method: 'POST',
    bodyJson: payload
  });

export const fetchAgentExecutions = async (agentId: string): Promise<ExecutionResult[]> =>
  requestJson<ExecutionResult[]>(`/agents/${agentId}/executions`);

export const deleteAgent = async (agentId: string): Promise<void> => {
  await requestJson<null>(`/agents/${agentId}`, {
    method: 'DELETE'
  });
};

export const streamRunAgent = async (
  agentId: string,
  payload: RunAgentPayload,
  callbacks: StreamCallbacks
): Promise<void> => {
  const response = await fetch(`${API_BASE_URL}/agents/${agentId}/run/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream'
    },
    body: JSON.stringify(payload)
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || `Request failed with status ${response.status}`);
  }

  if (!response.body) {
    throw new Error('Streaming is not supported in this browser.');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';

  const processEvent = (eventBlock: string): void => {
    const lines = eventBlock.split(/\r?\n/);
    let eventName = 'message';
    const dataLines: string[] = [];

    lines.forEach((line) => {
      if (line.startsWith('event:')) {
        eventName = line.slice('event:'.length).trim();
      } else if (line.startsWith('data:')) {
        dataLines.push(line.slice('data:'.length).trim());
      }
    });

    if (dataLines.length === 0) {
      return;
    }

    const dataText = dataLines.join('\n');
    let dataPayload: Record<string, unknown> = {};
    try {
      dataPayload = JSON.parse(dataText) as Record<string, unknown>;
    } catch {
      dataPayload = { message: dataText };
    }

    if (eventName === 'delta') {
      const contentValue = dataPayload.content;
      if (typeof contentValue === 'string' && contentValue.length > 0) {
        callbacks.onDelta(contentValue);
      }
      return;
    }

    if (eventName === 'error') {
      const messageValue = dataPayload.message;
      throw new Error(typeof messageValue === 'string' ? messageValue : 'Streaming request failed.');
    }

    if (eventName === 'done') {
      callbacks.onDone?.();
    }
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }

    buffer += decoder.decode(value, { stream: true });

    let separatorIndex = buffer.indexOf('\n\n');
    while (separatorIndex !== -1) {
      const eventBlock = buffer.slice(0, separatorIndex).trim();
      buffer = buffer.slice(separatorIndex + 2);

      if (eventBlock.length > 0) {
        processEvent(eventBlock);
      }

      separatorIndex = buffer.indexOf('\n\n');
    }
  }
};

export const streamAgentChat = async (
  agentId: string,
  payload: ChatStreamPayload,
  callbacks: StreamCallbacks
): Promise<void> => {
  const response = await fetch(`${API_BASE_URL}/agents/${agentId}/chat/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream'
    },
    body: JSON.stringify(payload)
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || `Request failed with status ${response.status}`);
  }

  if (!response.body) {
    throw new Error('Streaming is not supported in this browser.');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';

  const processEvent = (eventBlock: string): void => {
    const lines = eventBlock.split(/\r?\n/);
    let eventName = 'message';
    const dataLines: string[] = [];

    lines.forEach((line) => {
      if (line.startsWith('event:')) {
        eventName = line.slice('event:'.length).trim();
      } else if (line.startsWith('data:')) {
        dataLines.push(line.slice('data:'.length).trim());
      }
    });

    if (dataLines.length === 0) {
      return;
    }

    const dataText = dataLines.join('\n');
    let dataPayload: Record<string, unknown> = {};
    try {
      dataPayload = JSON.parse(dataText) as Record<string, unknown>;
    } catch {
      dataPayload = { message: dataText };
    }

    if (eventName === 'delta') {
      const contentValue = dataPayload.content;
      if (typeof contentValue === 'string' && contentValue.length > 0) {
        callbacks.onDelta(contentValue);
      }
      return;
    }

    if (eventName === 'error') {
      const messageValue = dataPayload.message;
      throw new Error(typeof messageValue === 'string' ? messageValue : 'Streaming request failed.');
    }

    if (eventName === 'done') {
      callbacks.onDone?.();
    }
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }

    buffer += decoder.decode(value, { stream: true });

    let separatorIndex = buffer.indexOf('\n\n');
    while (separatorIndex !== -1) {
      const eventBlock = buffer.slice(0, separatorIndex).trim();
      buffer = buffer.slice(separatorIndex + 2);

      if (eventBlock.length > 0) {
        processEvent(eventBlock);
      }

      separatorIndex = buffer.indexOf('\n\n');
    }
  }
};

export const uploadKnowledgeDocument = async (
  agentId: string,
  payload: KnowledgeDocumentPayload
): Promise<KnowledgeDocumentResult> =>
  requestJson<KnowledgeDocumentResult>(`/agents/${agentId}/knowledge/documents`, {
    method: 'POST',
    bodyJson: payload
  });
