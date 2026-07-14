import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { BacklogPanel } from './BacklogPanel';
import { fixtureBacklog } from '../test/fixtures';
import { TESTIDS } from '../test/fixtures';

describe('BacklogPanel', () => {
  it('renders empty state when backlog is null', () => {
    render(<BacklogPanel backlog={null} />);

    expect(screen.getByText('No backlog items')).toBeInTheDocument();
  });

  it('renders empty state when backlog has no tiers', () => {
    render(<BacklogPanel backlog={{ tiers: [] }} />);

    expect(screen.getByText('No backlog items')).toBeInTheDocument();
  });

  it('renders backlog title and audit tiers', () => {
    render(<BacklogPanel backlog={fixtureBacklog} />);

    expect(screen.getByText('Audit Backlog')).toBeInTheDocument();
    expect(screen.getByText('P0')).toBeInTheDocument();
    expect(screen.getByText('P1')).toBeInTheDocument();
  });

  it('displays tier counts (done, inflight, todo)', () => {
    render(<BacklogPanel backlog={fixtureBacklog} />);

    // P0 tier has done: 1, inflight: 1, todo: 1
    expect(screen.getByText('1 done, 1 inflight, 1 todo')).toBeInTheDocument();

    // P1 tier has done: 0, inflight: 0, todo: 1
    expect(screen.getByText('0 done, 0 inflight, 1 todo')).toBeInTheDocument();
  });

  it('renders progress bar segments with correct widths', () => {
    render(<BacklogPanel backlog={fixtureBacklog} />);

    const doneSegments = screen.getAllByLabelText(/done/);
    expect(doneSegments.length).toBeGreaterThan(0);

    // P0 has 1/3 done, so should be 33%
    const p0DoneSegment = doneSegments[0];
    expect(p0DoneSegment).toHaveStyle('width: 33.33333333333333%');
  });

  it('renders progress bar for all segment types', () => {
    render(<BacklogPanel backlog={fixtureBacklog} />);

    // P0 tier should have all three segment types
    const allSegments = screen.getAllByLabelText(/(done|in flight|to do)/);
    expect(allSegments.length).toBeGreaterThan(0);
  });

  it('renders all backlog items with status emoji and tags', () => {
    render(<BacklogPanel backlog={fixtureBacklog} />);

    // P0 items: "Origin fail-closed on /api/session", etc.
    expect(screen.getByText('Origin fail-closed on /api/session')).toBeInTheDocument();
    expect(screen.getByText('Dashboard rewrite foundation (U1)')).toBeInTheDocument();
    expect(screen.getByText('Cutover / to dist index (U9)')).toBeInTheDocument();

    // Check that tags are present
    expect(screen.getAllByText('[sec]').length).toBeGreaterThan(0);
    expect(screen.getAllByText('[ui]').length).toBeGreaterThan(0);
  });

  it('skips rendering tiers with zero items', () => {
    const emptyTier = {
      tier: 'P0' as const,
      items: [],
      done: 0,
      inflight: 0,
      todo: 0,
      total: 0,
    };

    const backlog = {
      tiers: [emptyTier, fixtureBacklog.tiers[0]],
    };

    render(<BacklogPanel backlog={backlog} />);

    // Should render P0 from fixture but not the empty one
    expect(screen.getByText('Dashboard rewrite foundation (U1)')).toBeInTheDocument();
  });

  it('has correct testid and renders panel container', () => {
    render(<BacklogPanel backlog={fixtureBacklog} />);

    const panel = screen.getByTestId(TESTIDS.backlogPanel);
    expect(panel).toBeInTheDocument();
  });

  it('status emojis have proper aria-labels', () => {
    render(<BacklogPanel backlog={fixtureBacklog} />);

    // Look for aria-labels on status emojis
    const statusSpans = screen.getAllByLabelText(/Done|In progress|To do|Blocked/);
    expect(statusSpans.length).toBeGreaterThan(0);

    statusSpans.forEach((span) => {
      expect(span).toHaveAttribute('aria-label');
    });
  });

  it('progress segments have proper titles and aria-labels', () => {
    render(<BacklogPanel backlog={fixtureBacklog} />);

    const doneSegments = screen.getAllByLabelText(/done/);
    doneSegments.forEach((segment) => {
      expect(segment).toHaveAttribute('title');
      expect(segment).toHaveAttribute('aria-label');
    });
  });

  it('renders P1 tier items correctly', () => {
    render(<BacklogPanel backlog={fixtureBacklog} />);

    // P1 items from fixture
    expect(screen.getByText('SSE keepalive tuning')).toBeInTheDocument();
    expect(screen.getByText('Hierarchical orchestration seams')).toBeInTheDocument();
  });
});
