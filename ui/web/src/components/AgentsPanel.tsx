/**
 * AgentsPanel — Fleet agents list with expandable rows.
 * Each agent row displays project · status · runtime at a glance.
 */

import type { Agent } from '../lib/types';
import { AgentRow } from './AgentRow';
import { TESTIDS } from '../test/fixtures';
import './AgentsPanel.css';

/**
 * Format runtime in seconds to a readable string.
 */
function formatRuntime(seconds: number | undefined): string {
  if (!seconds || seconds < 0) return 'unknown';
  if (seconds < 60) return `${Math.floor(seconds)}s`;
  const mins = Math.floor(seconds / 60);
  if (mins < 60) return `${mins}m`;
  const hours = Math.floor(seconds / 3600);
  return `${hours}h`;
}

interface AgentsPanelProps {
  agents: Agent[] | null;
}

export function AgentsPanel({ agents }: AgentsPanelProps) {
  if (!agents || agents.length === 0) {
    return (
      <section className="agents-panel" data-testid={TESTIDS.agentRow}>
        <h2>Fleet Agents</h2>
        <p className="empty-state">No agents running.</p>
      </section>
    );
  }

  return (
    <section className="agents-panel" data-testid={TESTIDS.agentRow}>
      <h2>Fleet Agents ({agents.length})</h2>
      <div className="agents-panel__summaries">
        {agents.map((agent) => (
          <div key={`${agent.id}-summary`} className="agent-summary">
            <span className="agent-summary__project">{agent.project}</span>
            <span className={`agent-summary__status agent-summary__status--${agent.status}`}>
              {agent.status}
            </span>
            <span className="agent-summary__runtime">{formatRuntime(agent.runtimeSeconds)}</span>
          </div>
        ))}
      </div>
      <ul className="agents-panel__list">
        {agents.map((agent) => (
          <AgentRow key={agent.id} agent={agent} />
        ))}
      </ul>
    </section>
  );
}
