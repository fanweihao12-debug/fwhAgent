import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { MessageItem } from '../types/agent';
import { formatTime } from '../utils/time';
import styles from './ChatMessage.module.css';

interface ChatMessageProps {
  message: MessageItem;
}

const roleToRowClass: Record<MessageItem['role'], string> = {
  user: styles.rowUser,
  assistant: styles.rowAssistant,
  system: styles.rowSystem
};

const roleToBubbleClass: Record<MessageItem['role'], string> = {
  user: styles.bubbleUser,
  assistant: styles.bubbleAssistant,
  system: styles.bubbleSystem
};

const roleToLabel: Record<MessageItem['role'], string> = {
  user: '你',
  assistant: 'Agent',
  system: '系统'
};

export const ChatMessage = ({ message }: ChatMessageProps) => {
  const isTyping = message.role === 'assistant' && message.status === 'typing';

  return (
    <div className={`${styles.row} ${roleToRowClass[message.role]}`}>
      <div className={`${styles.bubble} ${roleToBubbleClass[message.role]}`}>
        {message.role === 'assistant' ? (
          <div className={styles.markdownBody}>
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
            {isTyping ? <span className={styles.caret}>|</span> : null}
          </div>
        ) : (
          <div>{message.content}</div>
        )}

        <div className={styles.meta}>
          {roleToLabel[message.role]} · {formatTime(message.createdAt)}
        </div>
      </div>
    </div>
  );
};
