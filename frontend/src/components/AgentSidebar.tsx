import { useEffect, useState, type MouseEvent } from 'react';
import type { Agent } from '../types/agent';
import styles from './AgentSidebar.module.css';

interface AgentSidebarProps {
  agents: Agent[];
  selectedAgentId: string | null;
  deletingAgentId?: string | null;
  onStartNewChat: () => void;
  onDeleteAgent: (agent: Agent) => Promise<void>;
  onSelectAgent: (agentId: string) => void;
}

export const AgentSidebar = ({
  agents,
  selectedAgentId,
  deletingAgentId = null,
  onStartNewChat,
  onDeleteAgent,
  onSelectAgent
}: AgentSidebarProps) => {
  const [menuState, setMenuState] = useState<{ x: number; y: number; agent: Agent } | null>(null);
  const [confirmTarget, setConfirmTarget] = useState<Agent | null>(null);

  useEffect(() => {
    const closeMenu = (): void => {
      setMenuState(null);
    };

    window.addEventListener('click', closeMenu);
    return () => {
      window.removeEventListener('click', closeMenu);
    };
  }, []);

  const onAgentContextMenu = (event: MouseEvent<HTMLButtonElement>, agent: Agent): void => {
    event.preventDefault();
    setMenuState({
      x: event.clientX,
      y: event.clientY,
      agent
    });
  };

  const openDeleteConfirm = (): void => {
    if (!menuState) {
      return;
    }
    setConfirmTarget(menuState.agent);
    setMenuState(null);
  };

  const confirmDelete = async (): Promise<void> => {
    if (!confirmTarget) {
      return;
    }
    await onDeleteAgent(confirmTarget);
    setConfirmTarget(null);
  };

  return (
    <aside className={styles.panel}>
      <div className={styles.brand}>
        <p className={styles.brandTag}>FWH AGENT</p>
        <h1 className={styles.brandTitle}>Console</h1>
      </div>

      <button className={styles.newChatButton} type="button" onClick={onStartNewChat}>
        + 新建对话
      </button>

      <p className={styles.listTitle}>Agent 列表</p>

      <div className={styles.agentList}>
        {agents.map((agent) => {
          const selected = selectedAgentId === agent.id;
          return (
            <button
              key={agent.id}
              type="button"
              className={`${styles.agentItem} ${selected ? styles.agentItemSelected : ''}`}
              onClick={() => onSelectAgent(agent.id)}
              onContextMenu={(event) => onAgentContextMenu(event, agent)}
            >
              <p className={styles.agentName}>{agent.name}</p>
              <p className={styles.agentDescription}>{agent.description ?? '暂无描述'}</p>
            </button>
          );
        })}
      </div>

      {menuState ? (
        <div
          className={styles.contextMenu}
          style={{
            top: `${menuState.y}px`,
            left: `${menuState.x}px`
          }}
        >
          <button className={styles.contextMenuItemDanger} type="button" onClick={openDeleteConfirm}>
            删除
          </button>
        </div>
      ) : null}

      {confirmTarget ? (
        <div className={styles.modalMask}>
          <div className={styles.modal}>
            <p className={styles.modalTitle}>确认删除智能体</p>
            <p className={styles.modalText}>
              删除后将移除「{confirmTarget.name}」及其全部历史对话，且无法恢复。是否继续？
            </p>
            <div className={styles.modalActions}>
              <button className={styles.modalSecondaryButton} type="button" onClick={() => setConfirmTarget(null)}>
                取消
              </button>
              <button
                className={styles.modalDangerButton}
                type="button"
                onClick={() => void confirmDelete()}
                disabled={deletingAgentId === confirmTarget.id}
              >
                {deletingAgentId === confirmTarget.id ? '删除中...' : '确认删除'}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </aside>
  );
};
