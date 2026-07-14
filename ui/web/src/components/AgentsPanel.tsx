/**
 * AgentsPanel — Fleet agents list with expandable rows.
 */

import type { Agent } from '../lib/types';
import { AgentRow } from './AgentRow';
import { TESTIDS } from '../test/fixtures';
import './AgentsPanel.css';

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
      <ul className="agents-panel__list">
        {agents.map((agent) => (
          <AgentRow key={agent.id} agent={agent} />
        ))}
      </ul>
    </section>
  );
}
