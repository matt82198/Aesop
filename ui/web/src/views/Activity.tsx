/**
 * Activity view — Agent timeline + main-thread messages tail.
 * Read-only observability: shows agent execution spans and orchestrator reasoning.
 * Includes client-side status filter (All / Running / Error-Suspicious / Idle).
 */

import { useState } from 'react';
import Timeline from '../components/Timeline';
import MessagesTail from '../components/MessagesTail';
import DispatchPanel from '../components/DispatchPanel';
import { TESTIDS } from '../test/fixtures';
import type { SSEState } from '../lib/useSSE';
import type { Agent } from '../lib/types';
import styles from './Activity.module.css';

interface Props {
  state: Pick<SSEState, 'agents' | 'data'>;
}

type StatusFilter = 'all' | 'running' | 'error' | 'idle';

function filterAgentsByStatus(agents: Agent[], status: StatusFilter): Agent[] {
  if (status === 'all') return agents;
  if (status === 'running') return agents.filter(a => a.status === 'running');
  if (status === 'error') return agents.filter(a => a.status === 'SUSPICIOUS' || a.status === 'HIGH');
  if (status === 'idle') return agents.filter(a => a.status === 'idle');
  return agents;
}

export default function Activity({ state }: Props) {
  const agents = state.agents || [];
  const messages = state.data?.messages || [];
  const [filter, setFilter] = useState<StatusFilter>('all');

  const filteredAgents = filterAgentsByStatus(agents, filter);

  return (
    <div data-testid={TESTIDS.viewActivity} className={styles.container}>
      <section className={styles.section}>
        <DispatchPanel />
      </section>

      <section className={styles.section}>
        <div className={styles.timelineHeader}>
          <h3 className={styles.timelineTitle}>Agent Timeline</h3>
          <div className={styles.filterControls} data-testid="activity-status-filter">
            <button
              data-testid="filter-all"
              className={`${styles.filterButton} ${filter === 'all' ? styles.filterButtonActive : ''}`}
              onClick={() => setFilter('all')}
            >
              All ({agents.length})
            </button>
            <button
              data-testid="filter-running"
              className={`${styles.filterButton} ${filter === 'running' ? styles.filterButtonActive : ''}`}
              onClick={() => setFilter('running')}
            >
              Running
            </button>
            <button
              data-testid="filter-error"
              className={`${styles.filterButton} ${filter === 'error' ? styles.filterButtonActive : ''}`}
              onClick={() => setFilter('error')}
            >
              Error-Suspicious
            </button>
            <button
              data-testid="filter-idle"
              className={`${styles.filterButton} ${filter === 'idle' ? styles.filterButtonActive : ''}`}
              onClick={() => setFilter('idle')}
            >
              Idle
            </button>
          </div>
        </div>
        <Timeline agents={filteredAgents} />
      </section>

      <section className={styles.section}>
        <MessagesTail messages={messages} />
      </section>
    </div>
  );
}
