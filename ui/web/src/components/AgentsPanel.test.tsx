import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { AgentsPanel } from './AgentsPanel';
import { fixtureAgents, TESTIDS } from '../test/fixtures';

vi.mock('./AgentRow', () => ({
  AgentRow: ({ agent }: any) => <div data-testid="agent-row-mock">{agent.id}</div>,
}));

describe('AgentsPanel', () => {
  it('renders agents list with count', () => {
    render(<AgentsPanel agents={fixtureAgents} />);

    expect(screen.getByText(`Fleet Agents (${fixtureAgents.length})`)).toBeInTheDocument();
  });

  it('renders each agent row', () => {
    render(<AgentsPanel agents={fixtureAgents} />);

    const rows = screen.getAllByTestId('agent-row-mock');
    expect(rows).toHaveLength(fixtureAgents.length);
  });

  it('renders empty state when no agents', () => {
    render(<AgentsPanel agents={[]} />);

    expect(screen.getByText('No agents running.')).toBeInTheDocument();
  });

  it('renders empty state when agents is null', () => {
    render(<AgentsPanel agents={null} />);

    expect(screen.getByText('No agents running.')).toBeInTheDocument();
  });

  it('has correct data-testid', () => {
    render(<AgentsPanel agents={fixtureAgents} />);

    expect(screen.getByTestId(TESTIDS.agentRow)).toBeInTheDocument();
  });
});
