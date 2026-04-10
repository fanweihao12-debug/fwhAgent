import { useMutation } from '@tanstack/react-query';
import { runAgent } from '../api/agent';
import { useChatStore } from '../stores/chatStore';
import type { MessageItem } from '../types/agent';

const createMessage = (
  role: MessageItem['role'],
  content: string,
  status: MessageItem['status'] = 'done'
): MessageItem => ({
  id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
  role,
  content,
  createdAt: new Date().toISOString(),
  status
});

const parseAssistantText = (output: Record<string, unknown> | null): string => {
  if (!output) {
    return 'Agent returned empty output.';
  }

  const messageValue = output.message;
  if (typeof messageValue === 'string' && messageValue.trim().length > 0) {
    return messageValue;
  }

  return JSON.stringify(output, null, 2);
};

export const useAgentChat = () => {
  const { addMessage } = useChatStore();

  return useMutation({
    mutationFn: async ({ agentId, prompt }: { agentId: string; prompt: string }) => {
      const response = await runAgent(agentId, {
        input_data: {
          prompt
        }
      });
      return response;
    },
    onSuccess: (data, variables) => {
      const assistantText = parseAssistantText(data.output_data);
      addMessage(variables.agentId, createMessage('assistant', assistantText, 'typing'));
    },
    onError: (error, variables) => {
      const messageText = error instanceof Error ? error.message : 'Request failed. Please try again later.';
      addMessage(variables.agentId, createMessage('system', messageText, 'error'));
    }
  });
};
