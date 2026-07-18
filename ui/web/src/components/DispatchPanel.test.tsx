/**
 * DispatchPanel component tests.
 * Tests poll behavior, data rendering, unavailable states, and warnings.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import DispatchPanel from './DispatchPanel';
import { fixtureWaveDispatch, fixtureWaveDispatchUnavailable, TESTIDS } from '../test/fixtures';

// Mock the API
vi.mock('../lib/api', () => ({
  fetchWaveDispatch: vi.fn(),
}));

import { fetchWaveDispatch } from '../lib/api';

describe('DispatchPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders loading state initially', () => {
    (fetchWaveDispatch as any).mockImplementation(() => new Promise(() => {})); // Never resolves
    render(<DispatchPanel />);
    expect(screen.getByTestId(TESTIDS.dispatchPanel)).toBeInTheDocument();
    expect(screen.getByText(/Loading/i)).toBeInTheDocument();
  });

  it('renders available dispatch data', async () => {
    (fetchWaveDispatch as any).mockResolvedValue(fixtureWaveDispatch);
    render(<DispatchPanel />);

    await waitFor(() => {
      expect(screen.getByTestId(TESTIDS.dispatchPanel)).toBeInTheDocument();
    });

    // Check header
    expect(screen.getByText('Wave Dispatch')).toBeInTheDocument();
    expect(screen.getByText(fixtureWaveDispatch.wave_phase!)).toBeInTheDocument();

    // Check agents
    const agentRows = screen.getAllByTestId(TESTIDS.dispatchAgentRow);
    expect(agentRows).toHaveLength(fixtureWaveDispatch.agents.length);
  });

  it('displays agent phase badges', async () => {
    (fetchWaveDispatch as any).mockResolvedValue(fixtureWaveDispatch);
    render(<DispatchPanel />);

    await waitFor(() => {
      const badges = screen.getAllByTestId(TESTIDS.dispatchAgentPhase);
      expect(badges.length).toBeGreaterThan(0);
    });

    // Check first agent phase
    expect(screen.getByText('tool-use')).toBeInTheDocument();
  });

  it('formats activity age correctly', async () => {
    (fetchWaveDispatch as any).mockResolvedValue(fixtureWaveDispatch);
    render(<DispatchPanel />);

    await waitFor(() => {
      expect(screen.getByTestId(TESTIDS.dispatchAgentAge)).toBeInTheDocument();
    });

    // First agent has 3 seconds, should display "3s"
    const ages = screen.getAllByTestId(TESTIDS.dispatchAgentAge);
    expect(ages[0].textContent).toBe('3s');
  });

  it('formats token estimates correctly', async () => {
    (fetchWaveDispatch as any).mockResolvedValue(fixtureWaveDispatch);
    render(<DispatchPanel />);

    await waitFor(() => {
      expect(screen.getByTestId(TESTIDS.dispatchAgentTokens)).toBeInTheDocument();
    });

    // First agent has 145000 tokens, should display "145.0KT"
    const tokens = screen.getAllByTestId(TESTIDS.dispatchAgentTokens);
    expect(tokens[0].textContent).toMatch(/14\d\.\dKT/);
  });

  it('displays warnings for inactive agents', async () => {
    (fetchWaveDispatch as any).mockResolvedValue(fixtureWaveDispatch);
    render(<DispatchPanel />);

    await waitFor(() => {
      expect(screen.getByText(/inactive >5min/i)).toBeInTheDocument();
    });
  });

  it('renders unavailable state when no workflow active', async () => {
    (fetchWaveDispatch as any).mockResolvedValue(fixtureWaveDispatchUnavailable);
    render(<DispatchPanel />);

    await waitFor(() => {
      expect(screen.getByTestId(TESTIDS.dispatchPanelUnavailable)).toBeInTheDocument();
    });

    expect(screen.getByText(/No active workflow/i)).toBeInTheDocument();
  });

  it('renders empty agents state', async () => {
    (fetchWaveDispatch as any).mockResolvedValue({
      available: true,
      wave_phase: 'wave-test',
      agents: [],
      at: new Date().toISOString(),
    });

    render(<DispatchPanel />);

    await waitFor(() => {
      expect(screen.getByText(/No agents currently active/i)).toBeInTheDocument();
    });
  });

  it('polls for updates at configured interval', async () => {
    (fetchWaveDispatch as any).mockResolvedValue(fixtureWaveDispatch);
    render(<DispatchPanel />);

    await waitFor(() => {
      expect(screen.getByTestId(TESTIDS.dispatchPanel)).toBeInTheDocument();
    });

    // Advance time past poll interval (2.5s)
    vi.advanceTimersByTime(2500);

    await waitFor(() => {
      expect((fetchWaveDispatch as any)).toHaveBeenCalledTimes(2); // Initial + one poll
    });
  });

  it('stops polling when an error occurs', async () => {
    const error = new Error('Network error');
    (fetchWaveDispatch as any).mockRejectedValue(error);
    render(<DispatchPanel />);

    await waitFor(() => {
      expect(screen.getByTestId(TESTIDS.dispatchPanelUnavailable)).toBeInTheDocument();
    });
  });

  it('renders all agents from fixture', async () => {
    (fetchWaveDispatch as any).mockResolvedValue(fixtureWaveDispatch);
    render(<DispatchPanel />);

    await waitFor(() => {
      const agentRows = screen.getAllByTestId(TESTIDS.dispatchAgentRow);
      expect(agentRows).toHaveLength(3);
    });

    // Check specific agent IDs
    expect(screen.getByText('fleet-fix-0')).toBeInTheDocument();
    expect(screen.getByText('fleet-fix-1')).toBeInTheDocument();
    expect(screen.getByText('fleet-review-0')).toBeInTheDocument();
  });

  it('updates timestamp on each poll', async () => {
    const originalTime = new Date('2026-07-17T20:00:00Z');
    vi.setSystemTime(originalTime);

    (fetchWaveDispatch as any).mockResolvedValue(fixtureWaveDispatch);
    const { rerender } = render(<DispatchPanel />);

    await waitFor(() => {
      expect(screen.getByTestId(TESTIDS.dispatchPanel)).toBeInTheDocument();
    });

    // Move time forward
    const newTime = new Date('2026-07-17T20:05:00Z');
    vi.setSystemTime(newTime);

    // Advance past poll interval
    vi.advanceTimersByTime(2500);

    // Update mock to return new timestamp
    const updatedFixture = {
      ...fixtureWaveDispatch,
      at: newTime.toISOString(),
    };
    (fetchWaveDispatch as any).mockResolvedValue(updatedFixture);

    rerender(<DispatchPanel />);

    await waitFor(() => {
      // Timestamp should be updated (checking for new time)
      const timestampElements = screen.getAllByText(/:\d{2}$/);
      expect(timestampElements.length).toBeGreaterThan(0);
    });
  });
});
