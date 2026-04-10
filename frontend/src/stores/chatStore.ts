import { create } from 'zustand';
import type { MessageItem } from '../types/agent';

interface ChatState {
  selectedAgentId: string | null;
  messagesByAgentId: Record<string, MessageItem[]>;
  setSelectedAgentId: (agentId: string | null) => void;
  addMessage: (agentId: string, message: MessageItem) => void;
  updateMessage: (
    agentId: string,
    messageId: string,
    updater: (message: MessageItem) => MessageItem
  ) => void;
  setMessagesForAgent: (agentId: string, messages: MessageItem[]) => void;
  removeAgentData: (agentId: string) => void;
}

export const useChatStore = create<ChatState>((set) => ({
  selectedAgentId: null,
  messagesByAgentId: {},
  setSelectedAgentId: (agentId) => {
    set({ selectedAgentId: agentId });
  },
  addMessage: (agentId, message) => {
    set((state) => ({
      messagesByAgentId: {
        ...state.messagesByAgentId,
        [agentId]: [...(state.messagesByAgentId[agentId] ?? []), message]
      }
    }));
  },
  updateMessage: (agentId, messageId, updater) => {
    set((state) => ({
      messagesByAgentId: {
        ...state.messagesByAgentId,
        [agentId]: (state.messagesByAgentId[agentId] ?? []).map((message) =>
          message.id === messageId ? updater(message) : message
        )
      }
    }));
  },
  setMessagesForAgent: (agentId, messages) => {
    set((state) => ({
      messagesByAgentId: {
        ...state.messagesByAgentId,
        [agentId]: messages
      }
    }));
  },
  removeAgentData: (agentId) => {
    set((state) => {
      const nextMessagesByAgentId = { ...state.messagesByAgentId };
      delete nextMessagesByAgentId[agentId];

      return {
        selectedAgentId: state.selectedAgentId === agentId ? null : state.selectedAgentId,
        messagesByAgentId: nextMessagesByAgentId
      };
    });
  }
}));
