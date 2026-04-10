import type { ReactNode } from 'react';
import styles from './AgentLayout.module.css';

interface AgentLayoutProps {
  sidebar: ReactNode;
  children: ReactNode;
}

export const AgentLayout = ({ sidebar, children }: AgentLayoutProps) => (
  <div className={styles.page}>
    {sidebar}
    <main className={styles.main}>{children}</main>
  </div>
);
