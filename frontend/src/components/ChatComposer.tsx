import { useState } from 'react';
import styles from './ChatComposer.module.css';

interface ChatComposerProps {
  disabled?: boolean;
  onSubmit: (prompt: string) => void;
}

export const ChatComposer = ({ disabled = false, onSubmit }: ChatComposerProps) => {
  const [prompt, setPrompt] = useState('');

  const submitMessage = () => {
    const trimmedPrompt = prompt.trim();
    if (!trimmedPrompt) {
      return;
    }
    onSubmit(trimmedPrompt);
    setPrompt('');
  };

  return (
    <div className={styles.composerWrap}>
      <div className={styles.composer}>
        <textarea
          className={styles.input}
          value={prompt}
          onChange={(event) => setPrompt(event.target.value)}
          placeholder="输入你的问题，发送后自动新建对话..."
          disabled={disabled}
        />
        <button className={styles.sendButton} type="button" disabled={disabled} onClick={submitMessage}>
          发送
        </button>
      </div>
    </div>
  );
};
