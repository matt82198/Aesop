/**
 * AuditTailStream.test.tsx — component tests for audit tail stream.
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import AuditTailStream from './AuditTailStream';
import { TESTIDS, fixtureWaveAuditTail, fixtureWaveAuditTailUnavailable } from '../test/fixtures';

describe('AuditTailStream', () => {
  it('renders loading state initially', () => {
    const mockFetcher = vi.fn(() => new Promise(() => {}) as Promise<import('../lib/types').WaveAuditTailData>); // Never resolves
    render(<AuditTailStream fetcher={mockFetcher} />);
    expect(screen.getByTestId(TESTIDS.auditTail)).toBeInTheDocument();
    expect(screen.getByText('Loading...')).toBeInTheDocument();
  });

  it('renders with fixture data', async () => {
    const mockFetcher = vi.fn().mockResolvedValue(fixtureWaveAuditTail);
    render(<AuditTailStream fetcher={mockFetcher} />);

    await waitFor(() => {
      expect(screen.getByTestId(TESTIDS.auditTail)).toBeInTheDocument();
    });

    // Should render title
    expect(screen.getByText('Audit Tail')).toBeInTheDocument();

    // Should render audit items
    const items = screen.getAllByTestId(TESTIDS.auditTailItem);
    expect(items.length).toBe(5);
  });

  it('renders audit backlog items correctly', async () => {
    const mockFetcher = vi.fn().mockResolvedValue(fixtureWaveAuditTail);
    render(<AuditTailStream fetcher={mockFetcher} />);

    await waitFor(() => {
      expect(screen.getByTestId(TESTIDS.auditTail)).toBeInTheDocument();
    });

    // Should render audit item titles
    expect(screen.getByText('CSRF validation chain fixed')).toBeInTheDocument();
    expect(screen.getByText('SSE keepalive tuning in progress')).toBeInTheDocument();
    expect(screen.getByText('Timeline component edge case handling')).toBeInTheDocument();
  });

  it('renders verdict items correctly', async () => {
    const mockFetcher = vi.fn().mockResolvedValue(fixtureWaveAuditTail);
    render(<AuditTailStream fetcher={mockFetcher} />);

    await waitFor(() => {
      expect(screen.getByTestId(TESTIDS.auditTail)).toBeInTheDocument();
    });

    // Should render verdict items (OK and FAILED verdicts present)
    expect(screen.getByText('OK')).toBeInTheDocument();
    expect(screen.getByText('FAILED')).toBeInTheDocument();
  });

  it('renders tier and tag badges', async () => {
    const mockFetcher = vi.fn().mockResolvedValue(fixtureWaveAuditTail);
    render(<AuditTailStream fetcher={mockFetcher} />);

    await waitFor(() => {
      expect(screen.getByTestId(TESTIDS.auditTail)).toBeInTheDocument();
    });

    // Should render tier badges
    const p0 = screen.getAllByText('P0')[0];
    const p1 = screen.getAllByText('P1')[0];
    const p2 = screen.getAllByText('P2')[0];
    expect(p0).toBeInTheDocument();
    expect(p1).toBeInTheDocument();
    expect(p2).toBeInTheDocument();
  });

  it('renders unavailable state', async () => {
    const mockFetcher = vi.fn().mockResolvedValue(fixtureWaveAuditTailUnavailable);
    render(<AuditTailStream fetcher={mockFetcher} />);

    await waitFor(() => {
      expect(screen.getByText('(no recent audits)')).toBeInTheDocument();
    });
  });

  it('renders error message on fetch failure', async () => {
    const mockFetcher = vi.fn().mockRejectedValue(new Error('API error'));
    render(<AuditTailStream fetcher={mockFetcher} />);

    await waitFor(() => {
      expect(screen.getByText(/API error/)).toBeInTheDocument();
    });
  });

  it('fetches data on mount', async () => {
    const mockFetcher = vi.fn().mockResolvedValue(fixtureWaveAuditTail);
    render(<AuditTailStream fetcher={mockFetcher} />);

    await waitFor(() => {
      expect(mockFetcher).toHaveBeenCalledTimes(1);
    });
  });

  it('polls for data every 4 seconds when visible', async () => {
    const mockFetcher = vi.fn().mockResolvedValue(fixtureWaveAuditTail);
    vi.useFakeTimers({ shouldAdvanceTime: true });

    render(<AuditTailStream fetcher={mockFetcher} />);

    // Wait for initial load
    await waitFor(() => expect(mockFetcher).toHaveBeenCalled());
    mockFetcher.mockClear();

    // Advance timer by 4 seconds
    vi.advanceTimersByTime(4000);

    await waitFor(() => {
      expect(mockFetcher).toHaveBeenCalledTimes(1);
    });

    vi.useRealTimers();
  });
});
