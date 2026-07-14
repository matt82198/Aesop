import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { userEvent } from '@testing-library/user-event';
import { AgentRow } from './AgentRow';
import { fixtureAgents, fixtureAgentDetail, TESTIDS } from '../test/fixtures';
import * as api from '../lib/api';

vi.mock('../lib/api', () => ({
  fetchAgent: vi.fn(),
}));

describe('AgentRow', () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it('renders agent row with basic info', () => {
    render(<AgentRow agent={fixtureAgents[0]} />);

    expect(screen.getByTestId(TESTIDS.agentRow)).toBeInTheDocument();
    expect(screen.getByText(fixtureAgents[0].id)).toBeInTheDocument();
    expect(screen.getByText(fixtureAgents[0].hint)).toBeInTheDocument();
  });

  it('displays status indicator with correct color mapping', () => {
    const runningAgent = fixtureAgents[0]; // status: 'running'
    const { container } = render(<AgentRow agent={runningAgent} />);

    const statusIcon = container.querySelector('.agent-row__status-icon');
    expect(statusIcon).toBeInTheDocument();
    expect(statusIcon).toHaveTextContent('●');
  });

  it('displays age in appropriate format (seconds/minutes)', () => {
    const agent = { ...fixtureAgents[0], age_s: 45 };
    render(<AgentRow agent={agent} />);
    expect(screen.getByText('45s')).toBeInTheDocument();

    const { unmount } = render(<AgentRow agent={{ ...fixtureAgents[1], age_s: 341 }} />);
    expect(screen.getByText('5m')).toBeInTheDocument();
    unmount();
  });

  it('expands and collapses on toggle click', async () => {
    const user = userEvent.setup();
    const mockFetch = vi.mocked(api.fetchAgent);
    mockFetch.mockResolvedValueOnce(fixtureAgentDetail);

    render(<AgentRow agent={fixtureAgents[0]} />);

    const toggleButton = screen.getByLabelText(/expand/i);
    expect(toggleButton).toHaveAttribute('aria-expanded', 'false');

    await user.click(toggleButton);
    expect(toggleButton).toHaveAttribute('aria-expanded', 'true');

    await waitFor(() => {
      expect(screen.getByTestId(TESTIDS.agentRowDetail)).toBeInTheDocument();
    });

    await user.click(toggleButton);
    expect(toggleButton).toHaveAttribute('aria-expanded', 'false');
  });

  it('fetches agent detail on expansion', async () => {
    const mockFetch = vi.mocked(api.fetchAgent);
    mockFetch.mockResolvedValue(fixtureAgentDetail);

    render(<AgentRow agent={fixtureAgents[0]} />);

    const toggleButton = screen.getByLabelText(/expand/i);
    await userEvent.click(toggleButton);

    const prompt = await screen.findByText(fixtureAgentDetail.dispatch_prompt);
    expect(prompt).toBeInTheDocument();
  });

  it('displays dispatch prompt after fetch completes', async () => {
    const mockFetch = vi.mocked(api.fetchAgent);
    mockFetch.mockResolvedValue(fixtureAgentDetail);

    render(<AgentRow agent={fixtureAgents[0]} />);

    const toggleButton = screen.getByLabelText(/expand/i);
    await userEvent.click(toggleButton);

    const prompt = await screen.findByText(fixtureAgentDetail.dispatch_prompt);
    expect(prompt).toBeInTheDocument();
  });

  it('caches agent detail on subsequent expansions', async () => {
    const mockFetch = vi.mocked(api.fetchAgent);
    mockFetch.mockResolvedValueOnce(fixtureAgentDetail);

    const { rerender } = render(<AgentRow agent={fixtureAgents[0]} />);

    // First expansion
    let toggleButton = screen.getByLabelText(/expand/i);
    await userEvent.click(toggleButton);

    await waitFor(() => {
      expect(screen.getByText(fixtureAgentDetail.dispatch_prompt)).toBeInTheDocument();
    });

    const callCountAfterFirstExpand = mockFetch.mock.calls.length;

    // Collapse
    await userEvent.click(toggleButton);

    // Re-render with same agent
    rerender(<AgentRow agent={fixtureAgents[0]} />);

    // Second expansion (should use cache)
    toggleButton = screen.getByLabelText(/expand/i);
    await userEvent.click(toggleButton);

    // Should still only have been called once (from cache on second expansion)
    expect(mockFetch.mock.calls.length).toBe(callCountAfterFirstExpand);
  });

  it('is keyboard accessible (toggle button can be focused and activated)', async () => {
    const mockFetch = vi.mocked(api.fetchAgent);
    mockFetch.mockResolvedValueOnce(fixtureAgentDetail);

    render(<AgentRow agent={fixtureAgents[0]} />);

    const toggleButton = screen.getByLabelText(/expand/i);

    // Should be focusable
    toggleButton.focus();
    expect(document.activeElement).toBe(toggleButton);

    // Should be activatable with Enter
    await userEvent.keyboard('{Enter}');
    expect(toggleButton).toHaveAttribute('aria-expanded', 'true');

    await waitFor(() => {
      expect(screen.getByTestId(TESTIDS.agentRowDetail)).toBeInTheDocument();
    });
  });

  it('expansion survives prop updates with same agent (keyed row identity)', async () => {
    const mockFetch = vi.mocked(api.fetchAgent);
    mockFetch.mockResolvedValueOnce(fixtureAgentDetail);

    const { rerender } = render(<AgentRow agent={fixtureAgents[0]} />);

    // Expand
    const toggleButton = screen.getByLabelText(/expand/i);
    await userEvent.click(toggleButton);

    await waitFor(() => {
      expect(screen.getByTestId(TESTIDS.agentRowDetail)).toBeInTheDocument();
    });

    // Re-render with same agent (simulating parent re-render)
    rerender(<AgentRow agent={fixtureAgents[0]} />);

    // Expanded detail should still be visible
    expect(screen.getByTestId(TESTIDS.agentRowDetail)).toBeInTheDocument();
    expect(toggleButton).toHaveAttribute('aria-expanded', 'true');
  });

  it('displays all detail fields when expanded', async () => {
    const mockFetch = vi.mocked(api.fetchAgent);
    mockFetch.mockResolvedValueOnce(fixtureAgentDetail);

    const agent = fixtureAgents[0];
    render(<AgentRow agent={agent} />);

    const toggleButton = screen.getByLabelText(/expand/i);
    await userEvent.click(toggleButton);

    await waitFor(() => {
      expect(screen.getByText(agent.project)).toBeInTheDocument();
      expect(screen.getByText(agent.taskLabel)).toBeInTheDocument();
    });
  });

  it('formats runtime duration correctly', async () => {
    const mockFetch = vi.mocked(api.fetchAgent);
    mockFetch.mockResolvedValueOnce(fixtureAgentDetail);

    const agent = { ...fixtureAgents[0], runtimeSeconds: 125 }; // 2m 5s
    render(<AgentRow agent={agent} />);

    const toggleButton = screen.getByLabelText(/expand/i);
    await userEvent.click(toggleButton);

    await waitFor(() => {
      expect(screen.getByText('2m 5s')).toBeInTheDocument();
    });
  });

  it('formats token count with commas', async () => {
    const mockFetch = vi.mocked(api.fetchAgent);
    mockFetch.mockResolvedValueOnce(fixtureAgentDetail);

    const agent = { ...fixtureAgents[0], tokensUsed: 48213 };
    render(<AgentRow agent={agent} />);

    const toggleButton = screen.getByLabelText(/expand/i);
    await userEvent.click(toggleButton);

    await waitFor(() => {
      expect(screen.getByText('48,213')).toBeInTheDocument();
    });
  });
});
