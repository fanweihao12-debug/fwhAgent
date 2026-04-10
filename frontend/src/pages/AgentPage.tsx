import { useEffect, useRef, useState, type ChangeEvent } from 'react';
import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  createAgent,
  deleteAgent,
  fetchAgentExecutions,
  fetchAgentList,
  fetchKnowledgeIngestJob,
  streamAgentChat,
  uploadKnowledgePdf
} from '../api/agent';
import { AgentSidebar } from '../components/AgentSidebar';
import { ChatComposer } from '../components/ChatComposer';
import { ChatMessage } from '../components/ChatMessage';
import { AgentLayout } from '../layouts/AgentLayout';
import { useChatStore } from '../stores/chatStore';
import type { Agent, ExecutionResult, MessageItem } from '../types/agent';
import styles from './AgentPage.module.css';

const createMessage = (
  role: MessageItem['role'],
  content: string,
  status: MessageItem['status'],
  createdAt: string,
  id: string
): MessageItem => ({
  id,
  role,
  content,
  status,
  createdAt
});

const AGENT_NAME_MAX_LENGTH = 120;
const PDF_UPLOAD_MAX_SIZE_BYTES = 20 * 1024 * 1024;
const JOB_POLL_INTERVAL_MS = 2000;

const normalizeAgentName = (prompt: string): string => {
  const trimmedPrompt = prompt.trim();
  if (trimmedPrompt.length <= AGENT_NAME_MAX_LENGTH) {
    return trimmedPrompt;
  }
  return trimmedPrompt.slice(0, AGENT_NAME_MAX_LENGTH);
};

const formatInputPrompt = (inputData: Record<string, unknown>): string => {
  const prompt = inputData.prompt;
  if (typeof prompt === 'string' && prompt.trim().length > 0) {
    return prompt;
  }
  return JSON.stringify(inputData, null, 2);
};

const formatOutputMessage = (execution: ExecutionResult): { role: MessageItem['role']; content: string } => {
  if (execution.status === 'failed') {
    return {
      role: 'system',
      content: execution.error ?? 'Agent execution failed.'
    };
  }

  const outputData = execution.output_data;
  if (!outputData) {
    return {
      role: 'assistant',
      content: 'Agent returned empty output.'
    };
  }

  const outputMessage = outputData.message;
  if (typeof outputMessage === 'string' && outputMessage.trim().length > 0) {
    return {
      role: 'assistant',
      content: outputMessage
    };
  }

  return {
    role: 'assistant',
    content: JSON.stringify(outputData, null, 2)
  };
};

const mapExecutionsToMessages = (executions: ExecutionResult[]): MessageItem[] => {
  const messages: MessageItem[] = [];

  executions.forEach((execution) => {
    messages.push(
      createMessage(
        'user',
        formatInputPrompt(execution.input_data),
        'done',
        execution.started_at ?? execution.created_at,
        `${execution.id}-user`
      )
    );

    const output = formatOutputMessage(execution);
    messages.push(
      createMessage(
        output.role,
        output.content,
        output.role === 'system' ? 'error' : 'done',
        execution.finished_at ?? execution.created_at,
        `${execution.id}-assistant`
      )
    );
  });

  return messages;
};

export const AgentPage = () => {
  const queryClient = useQueryClient();
  const [isStreaming, setIsStreaming] = useState(false);
  const [isCreatingNewChat, setIsCreatingNewChat] = useState(false);
  const [isUploadingPdf, setIsUploadingPdf] = useState(false);
  const [knowledgeStatusText, setKnowledgeStatusText] = useState('');

  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const pollTimerRef = useRef<number | null>(null);
  const isPollingRef = useRef(false);

  const { data: agents = [] } = useQuery({
    queryKey: ['agents'],
    queryFn: fetchAgentList
  });

  const executionQueries = useQueries({
    queries: agents.map((agent) => ({
      queryKey: ['agent-executions', agent.id],
      queryFn: () => fetchAgentExecutions(agent.id)
    }))
  });

  const createAgentMutation = useMutation({
    mutationFn: createAgent,
    onSuccess: (createdAgent) => {
      queryClient.setQueryData<Agent[]>(['agents'], (currentList) => {
        if (!currentList) {
          return [createdAgent];
        }
        const exists = currentList.some((item) => item.id === createdAgent.id);
        return exists ? currentList : [createdAgent, ...currentList];
      });
      void queryClient.invalidateQueries({ queryKey: ['agents'] });
    }
  });

  const deleteAgentMutation = useMutation({
    mutationFn: deleteAgent
  });

  const {
    selectedAgentId,
    setSelectedAgentId,
    addMessage,
    updateMessage,
    setMessagesForAgent,
    removeAgentData,
    messagesByAgentId
  } = useChatStore();

  useEffect(() => {
    executionQueries.forEach((query, index) => {
      const agent = agents[index];
      if (!agent || !query.data) {
        return;
      }

      const existingMessages = messagesByAgentId[agent.id];
      if (existingMessages !== undefined) {
        return;
      }

      setMessagesForAgent(agent.id, mapExecutionsToMessages(query.data));
    });
  }, [agents, executionQueries, messagesByAgentId, setMessagesForAgent]);

  useEffect(() => {
    if (!isCreatingNewChat && !selectedAgentId && agents.length > 0) {
      setSelectedAgentId(agents[0].id);
    }
  }, [agents, isCreatingNewChat, selectedAgentId, setSelectedAgentId]);

  useEffect(
    () => () => {
      if (pollTimerRef.current !== null) {
        window.clearInterval(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    },
    []
  );

  const currentMessages = selectedAgentId ? messagesByAgentId[selectedAgentId] ?? [] : [];

  const runPrompt = async (agentId: string, prompt: string): Promise<void> => {
    const userMessageId = `${Date.now()}-user-${Math.random()}`;
    const assistantMessageId = `${Date.now()}-assistant-${Math.random()}`;

    addMessage(agentId, createMessage('user', prompt, 'done', new Date().toISOString(), userMessageId));
    addMessage(agentId, createMessage('assistant', '', 'typing', new Date().toISOString(), assistantMessageId));

    const charQueue: string[] = [];
    let streamCompleted = false;
    let resolveTypingComplete: (() => void) | null = null;
    const typingCompletePromise = new Promise<void>((resolve) => {
      resolveTypingComplete = resolve;
    });

    const typingTimer = setInterval(() => {
      if (charQueue.length > 0) {
        const nextChar = charQueue.shift();
        if (nextChar) {
          updateMessage(agentId, assistantMessageId, (message) => ({
            ...message,
            content: message.content + nextChar
          }));
        }
        return;
      }

      if (streamCompleted) {
        clearInterval(typingTimer);
        updateMessage(agentId, assistantMessageId, (message) => ({
          ...message,
          status: 'done'
        }));
        resolveTypingComplete?.();
      }
    }, 14);

    setIsStreaming(true);
    try {
      await streamAgentChat(
        agentId,
        {
          message: prompt,
          top_k: 4
        },
        {
          onDelta: (chunk) => {
            charQueue.push(...Array.from(chunk));
          },
          onDone: () => {
            streamCompleted = true;
          }
        }
      );
      streamCompleted = true;
      await typingCompletePromise;
    } catch (error) {
      clearInterval(typingTimer);
      const messageText = error instanceof Error ? error.message : 'Streaming request failed.';
      updateMessage(agentId, assistantMessageId, (message) => ({
        ...message,
        role: 'system',
        content: messageText,
        status: 'error'
      }));
    } finally {
      setIsStreaming(false);
      void queryClient.invalidateQueries({ queryKey: ['agent-executions', agentId] });
    }
  };

  const submitPrompt = async (prompt: string): Promise<void> => {
    if (selectedAgentId) {
      await runPrompt(selectedAgentId, prompt);
      return;
    }

    try {
      const createdAgent = await createAgentMutation.mutateAsync({
        name: normalizeAgentName(prompt),
        description: null
      });

      setIsCreatingNewChat(false);
      setSelectedAgentId(createdAgent.id);
      await runPrompt(createdAgent.id, prompt);
    } catch {
      // The request error is handled by React Query state and network logs.
    }
  };

  const onDeleteAgent = async (agent: Agent): Promise<void> => {
    await deleteAgentMutation.mutateAsync(agent.id);

    queryClient.setQueryData<Agent[]>(['agents'], (currentList) => {
      if (!currentList) {
        return [];
      }
      return currentList.filter((item) => item.id !== agent.id);
    });
    queryClient.removeQueries({ queryKey: ['agent-executions', agent.id] });

    removeAgentData(agent.id);

    const nextAgents = queryClient.getQueryData<Agent[]>(['agents']) ?? [];
    if (selectedAgentId === agent.id) {
      setSelectedAgentId(nextAgents[0]?.id ?? null);
    }

    void queryClient.invalidateQueries({ queryKey: ['agents'] });
  };

  const clearJobPollTimer = (): void => {
    if (pollTimerRef.current !== null) {
      window.clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  };

  const startPollingKnowledgeJob = (agentId: string, jobId: string): void => {
    clearJobPollTimer();
    isPollingRef.current = false;

    pollTimerRef.current = window.setInterval(() => {
      if (isPollingRef.current) {
        return;
      }

      isPollingRef.current = true;
      void fetchKnowledgeIngestJob(agentId, jobId)
        .then((job) => {
          if (job.status === 'success') {
            clearJobPollTimer();
            setKnowledgeStatusText(`PDF已入库，切片数：${job.chunk_count ?? 0}`);
            return;
          }

          if (job.status === 'failed') {
            clearJobPollTimer();
            setKnowledgeStatusText(`PDF入库失败：${job.error_message ?? '未知错误'}`);
            return;
          }

          setKnowledgeStatusText(`PDF处理中（状态：${job.status}）...`);
        })
        .catch((error) => {
          clearJobPollTimer();
          const messageText = error instanceof Error ? error.message : '轮询任务状态失败';
          setKnowledgeStatusText(messageText);
        })
        .finally(() => {
          isPollingRef.current = false;
        });
    }, JOB_POLL_INTERVAL_MS);
  };

  const onClickUploadPdf = (): void => {
    if (!selectedAgentId) {
      setKnowledgeStatusText('请先选择一个对话，再上传PDF。');
      return;
    }

    fileInputRef.current?.click();
  };

  const onSelectPdfFile = async (event: ChangeEvent<HTMLInputElement>): Promise<void> => {
    const selectedFile = event.target.files?.[0];
    event.target.value = '';

    if (!selectedFile) {
      return;
    }

    if (!selectedAgentId) {
      setKnowledgeStatusText('请先选择一个对话，再上传PDF。');
      return;
    }

    if (selectedFile.size > PDF_UPLOAD_MAX_SIZE_BYTES) {
      setKnowledgeStatusText('PDF文件大小不能超过20MB。');
      return;
    }

    setIsUploadingPdf(true);
    setKnowledgeStatusText('PDF上传中...');
    try {
      const uploadResult = await uploadKnowledgePdf(selectedAgentId, selectedFile);
      setKnowledgeStatusText(`PDF上传成功，任务已入队（${uploadResult.job_id}），正在处理...`);
      startPollingKnowledgeJob(selectedAgentId, uploadResult.job_id);
    } catch (error) {
      const messageText = error instanceof Error ? error.message : 'PDF上传失败';
      setKnowledgeStatusText(messageText);
    } finally {
      setIsUploadingPdf(false);
    }
  };

  const isBusy = isStreaming || createAgentMutation.isPending || isUploadingPdf;

  const onStartNewChat = (): void => {
    setIsCreatingNewChat(true);
    setSelectedAgentId(null);
  };

  const onSelectExistingAgent = (agentId: string): void => {
    setIsCreatingNewChat(false);
    setSelectedAgentId(agentId);
  };

  return (
    <AgentLayout
      sidebar={
        <AgentSidebar
          agents={agents}
          selectedAgentId={selectedAgentId}
          deletingAgentId={deleteAgentMutation.variables ?? null}
          onStartNewChat={onStartNewChat}
          onDeleteAgent={onDeleteAgent}
          onSelectAgent={onSelectExistingAgent}
        />
      }
    >
      <section className={styles.wrap}>
        <header className={styles.titleBar}>
          <h2 className={styles.title}>What can the Agent help with today?</h2>
          <div className={styles.knowledgeToolbar}>
            <input
              ref={fileInputRef}
              className={styles.hiddenFileInput}
              type="file"
              accept=".pdf,application/pdf"
              onChange={(event) => void onSelectPdfFile(event)}
            />
            <button
              className={styles.uploadButton}
              type="button"
              disabled={isUploadingPdf || !selectedAgentId}
              onClick={onClickUploadPdf}
            >
              {isUploadingPdf ? '上传中...' : '上传PDF'}
            </button>
            {knowledgeStatusText ? <p className={styles.knowledgeStatus}>{knowledgeStatusText}</p> : null}
          </div>
        </header>

        <div className={styles.conversation}>
          {currentMessages.length === 0 ? (
            <div className={styles.emptyState}>
              {selectedAgentId ? <p>Send a message to continue this chat.</p> : <p>Send a first message to start a new chat.</p>}
            </div>
          ) : (
            currentMessages.map((message) => <ChatMessage key={message.id} message={message} />)
          )}
        </div>

        <ChatComposer disabled={isBusy} onSubmit={(prompt) => void submitPrompt(prompt)} />
      </section>
    </AgentLayout>
  );
};
