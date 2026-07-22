/**
 * ReasoningTail.test.tsx — component tests for reasoning transparency tail.
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import ReasoningTail from './ReasoningTail';
import { TESTIDS, fixtureWaveReasoningTail, fixtureWaveReasoningTailUnavailable } from '../test/fixtures';

describe('ReasoningTail', () => {
  it('renders loading state initially', () => {
    const mockFetcher = vi.fn(() => new Promise(() => {}) as Promise<import('../lib/types').WaveReasoningTailData>); // Never resolves
    render(<ReasoningTail fetcher={mockFetcher} />);
    expect(screen.getByTestId(TESTIDS.reasoningTail)).toBeInTheDocument();
    expect(screen.getByText('Loading...')).toBeInTheDocument();
  });

  it('renders with fixture data', async () => {
    const mockFetcher = vi.fn().mockResolvedValue(fixtureWaveReasoningTail);
    render(<ReasoningTail fetcher={mockFetcher} />);

    await waitFor(() => {
      expect(screen.getByTestId(TESTIDS.reasoningTail)).toBeInTheDocument();
    });

    // Should render title
    expect(screen.getByText('Reasoning Transparency')).toBeInTheDocument();

    // Should render agent cards
    const agents = screen.getAllByTestId(TESTIDS.reasoningTailAgent);
    expect(agents.length).toBe(3);
  });

  it('renders agent IDs and phases', async () => {
    const mockFetcher = vi.fn().mockResolvedValue(fixtureWaveReasoningTail);
    render(<ReasoningTail fetcher={mockFetcher} />);

    await waitFor(() => {
      expect(screen.getByTestId(TESTIDS.reasoningTail)).toBeInTheDocument();
    });

    // Should render agent IDs
    expect(screen.getByText('fleet-fix-0')).toBeInTheDocument();
    expect(screen.getByText('fleet-fix-1')).toBeInTheDocument();
    expect(screen.getByText('fleet-review-0')).toBeInTheDocument();

    // Should render phases
    expect(screen.getByText('tool-use')).toBeInTheDocument();
    expect(screen.getByText('stall')).toBeInTheDocument();
    expect(screen.getByText('thinking')).toBeInTheDocument();
  });

  it('renders reasoning summaries', async () => {
    const mockFetcher = vi.fn().mockResolvedValue(fixtureWaveReasoningTail);
    render(<ReasoningTail fetcher={mockFetcher} />);

    await waitFor(() => {
      expect(screen.getByTestId(TESTIDS.reasoningTail)).toBeInTheDocument();
    });

    // Should render reasoning strings
    expect(screen.getByText('thinking → tool:edit → result → thinking')).toBeInTheDocument();
    expect(screen.getByText(/tool:bash/)).toBeInTheDocument();
  });

  it('renders token estimates', async () => {
    const mockFetcher = vi.fn().mockResolvedValue(fixtureWaveReasoningTail);
    render(<ReasoningTail fetcher={mockFetcher} />);

    await waitFor(() => {
      expect(screen.getByTestId(TESTIDS.reasoningTail)).toBeInTheDocument();
    });

    // Should render token counts in K
    expect(screen.getByText('145K')).toBeInTheDocument();
    expect(screen.getByText('89K')).toBeInTheDocument();
    expect(screen.getByText('77K')).toBeInTheDocument();
  });

  it('renders activity age', async () => {
    const mockFetcher = vi.fn().mockResolvedValue(fixtureWaveReasoningTail);
    render(<ReasoningTail fetcher={mockFetcher} />);

    await waitFor(() => {
      expect(screen.getByTestId(TESTIDS.reasoningTail)).toBeInTheDocument();
    });

    // Should render age in seconds/minutes
    expect(screen.getByText('3s')).toBeInTheDocument();
    expect(screen.getByText('7m')).toBeInTheDocument();
    expect(screen.getByText('12s')).toBeInTheDocument();
  });

  it('renders warning badges for stalled agents', async () => {
    const mockFetcher = vi.fn().mockResolvedValue(fixtureWaveReasoningTail);
    render(<ReasoningTail fetcher={mockFetcher} />);

    await waitFor(() => {
      expect(screen.getByTestId(TESTIDS.reasoningTail)).toBeInTheDocument();
    });

    // Should render warnings for fleet-fix-1
    expect(screen.getByText('inactive >5min')).toBeInTheDocument();
    expect(screen.getByText('stalled >10min')).toBeInTheDocument();
  });

  it('renders unavailable state', async () => {
    const mockFetcher = vi.fn().mockResolvedValue(fixtureWaveReasoningTailUnavailable);
    render(<ReasoningTail fetcher={mockFetcher} />);

    await waitFor(() => {
      expect(screen.getByText('(no active agents)')).toBeInTheDocument();
    });
  });

  it('renders error message on fetch failure', async () => {
    const mockFetcher = vi.fn().mockRejectedValue(new Error('Fetch error'));
    render(<ReasoningTail fetcher={mockFetcher} />);

    await waitFor(() => {
      expect(screen.getByText(/Fetch error/)).toBeInTheDocument();
    });
  });

  it('fetches data on mount', async () => {
    const mockFetcher = vi.fn().mockResolvedValue(fixtureWaveReasoningTail);
    render(<ReasoningTail fetcher={mockFetcher} />);

    await waitFor(() => {
      expect(mockFetcher).toHaveBeenCalledTimes(1);
    });
  });

  it('polls for data every 2.5 seconds when visible', async () => {
    const mockFetcher = vi.fn().mockResolvedValue(fixtureWaveReasoningTail);
    vi.useFakeTimers({ shouldAdvanceTime: true });

    render(<ReasoningTail fetcher={mockFetcher} />);

    // Wait for initial load
    await waitFor(() => expect(mockFetcher).toHaveBeenCalled());
    mockFetcher.mockClear();

    // Advance timer by 2.5 seconds
    vi.advanceTimersByTime(2500);

    await waitFor(() => {
      expect(mockFetcher).toHaveBeenCalledTimes(1);
    });

    vi.useRealTimers();
  });
});
