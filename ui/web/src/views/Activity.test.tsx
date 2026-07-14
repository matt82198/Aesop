/**
 * Activity view — agent timeline + main-thread messages tail.
 */

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import Activity from './Activity';
import { fixtureAgents, fixtureMessages } from '../test/fixtures';
import { TESTIDS } from '../test/fixtures';
import type { FullState } from '../lib/types';

describe('Activity view', () => {
  const fixtureState: FullState = {
    data: {
      watchdog: { alive: 'ALIVE', age: 3, threshold: 300 },
      monitor: { alive: 'ALIVE', age: 45, threshold: 3600 },
      agents: fixtureAgents,
      repos: [],
      events: [],
      alerts: { count: 0, lines: [] },
      messages: fixtureMessages,
    },
    backlog: { tiers: [] },
    agents: fixtureAgents,
    tracker: { items: [] },
    status: { orchestrators: [] },
  };

  it('renders activity view container with testid', () => {
    render(<Activity state={fixtureState} />);
    expect(screen.getByTestId(TESTIDS.viewActivity)).toBeInTheDocument();
  });

  it('renders timeline component with agents', () => {
    render(<Activity state={fixtureState} />);
    expect(screen.getByTestId(TESTIDS.timeline)).toBeInTheDocument();
    // Timeline should render agent ids
    fixtureAgents.forEach((agent) => {
      expect(screen.getByText(agent.id)).toBeInTheDocument();
    });
  });

  it('renders messages tail component', () => {
    render(<Activity state={fixtureState} />);
    expect(screen.getByTestId(TESTIDS.messagesTail)).toBeInTheDocument();
    // Should render messages
    expect(screen.getByText(/Run wave 14/)).toBeInTheDocument();
  });

  it('shows empty state when no agents or messages', () => {
    const emptyState: FullState = {
      ...fixtureState,
      agents: [],
      data: {
        ...fixtureState.data,
        agents: [],
        messages: [],
      },
    };
    render(<Activity state={emptyState} />);
    const timeline = screen.getByTestId(TESTIDS.timeline);
    expect(timeline.textContent).toContain('no agents');
  });

  it('handles partial data gracefully (no messages)', () => {
    const partialState: FullState = {
      ...fixtureState,
      data: {
        ...fixtureState.data,
        messages: [],
      },
    };
    render(<Activity state={partialState} />);
    expect(screen.getByTestId(TESTIDS.viewActivity)).toBeInTheDocument();
    const messagesTail = screen.getByTestId(TESTIDS.messagesTail);
    expect(messagesTail.textContent).toContain('no messages');
  });

  it('renders timeline above messages (visual hierarchy)', () => {
    render(<Activity state={fixtureState} />);
    const timeline = screen.getByTestId(TESTIDS.timeline);
    const messagesTail = screen.getByTestId(TESTIDS.messagesTail);

    // Timeline should appear before messages in DOM (by finding their positions)
    const timelinePosition = timeline.compareDocumentPosition(messagesTail);
    // DOCUMENT_POSITION_FOLLOWING = 4, meaning timeline comes before messages
    expect(timelinePosition & 4).toBe(4);
  });
});
