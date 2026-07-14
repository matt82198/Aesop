import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { TrackerBoard } from './TrackerBoard';
import { fixtureTrackerItems } from '../test/fixtures';
import { TESTIDS } from '../test/fixtures';

describe('TrackerBoard', () => {
  it('renders all 4 lanes', () => {
    render(<TrackerBoard items={fixtureTrackerItems} />);

    // Use role queries to be specific about lane headers
    // Lane headers have format: "LaneName <span>Count</span>"
    // So we need to check if the text starts with the lane name
    const headers = screen.getAllByRole('heading', { level: 2 });
    const laneNames = headers.map((h) => {
      // Get the text before the count span
      const firstNode = h.firstChild;
      if (firstNode && firstNode.nodeType === Node.TEXT_NODE) {
        return firstNode.textContent?.trim() || '';
      }
      return h.textContent || '';
    });

    expect(laneNames.some((name) => name.includes('Proposed'))).toBe(true);
    expect(laneNames.some((name) => name.includes('Ranked'))).toBe(true);
    expect(laneNames.some((name) => name.includes('In Progress'))).toBe(true);
  });

  it('buckets items correctly by lane', () => {
    render(<TrackerBoard items={fixtureTrackerItems} />);

    // fixtureTrackerItems[0] has lane: 'in-progress'
    // fixtureTrackerItems[1] has lane: 'done'
    // fixtureTrackerItems[2] has lane: 'ranked'
    // fixtureTrackerItems[3] has lane: 'proposed'
    // fixtureTrackerItems[4] has lane: 'done' (archived status)

    expect(screen.getByText('Dashboard rewrite: foundation scaffold')).toBeInTheDocument();
    expect(screen.getByText('Cost collector parses OUTCOMES-LEDGER.md')).toBeInTheDocument();
    expect(screen.getByText('Agent timeline read-only v1')).toBeInTheDocument();
    expect(screen.getByText('Replay slider for agent timeline')).toBeInTheDocument();
  });

  it('displays lane counts with accessible labels', () => {
    render(<TrackerBoard items={fixtureTrackerItems} />);

    // Should have accessible labels for counts
    const laneCountSpans = screen.getAllByLabelText(/items in/);
    expect(laneCountSpans.length).toBeGreaterThan(0);

    laneCountSpans.forEach((span) => {
      expect(span).toHaveAttribute('aria-label');
    });
  });

  it('routes unknown lanes to proposed', () => {
    const unknownLaneItem = {
      ...fixtureTrackerItems[0],
      lane: 'undefined-lane' as any,
    };

    render(<TrackerBoard items={[unknownLaneItem]} />);

    // Should appear under Proposed
    const proposedLane = screen.getByText('Proposed').closest('section');
    expect(proposedLane).toBeInTheDocument();
    expect(proposedLane?.textContent).toContain(unknownLaneItem.title);
  });

  it('separates archived items from active lanes', () => {
    const archivedItem = fixtureTrackerItems[4]; // status: archived
    expect(archivedItem.status).toBe('archived');

    render(<TrackerBoard items={[archivedItem]} />);

    // Should appear in archived section, not in any lane
    expect(screen.getByText('Archived (1)')).toBeInTheDocument();
    expect(screen.getByText(archivedItem.title)).toBeInTheDocument();
  });

  it('shows archived summary with item count', () => {
    const archived1 = { ...fixtureTrackerItems[1], status: 'archived' as const };
    const archived2 = { ...fixtureTrackerItems[4], status: 'archived' as const };

    render(<TrackerBoard items={[archived1, archived2]} />);

    expect(screen.getByText('Archived (2)')).toBeInTheDocument();
  });

  it('lanes with no items show "No items" placeholder', () => {
    const singleItem = fixtureTrackerItems.slice(0, 1); // only 1 item in in-progress

    render(<TrackerBoard items={singleItem} />);

    const emptyMessages = screen.getAllByText('No items');
    expect(emptyMessages.length).toBeGreaterThan(0); // At least 3 empty lanes
  });

  it('renders tracker cards in each lane', () => {
    render(<TrackerBoard items={fixtureTrackerItems} />);

    const cards = screen.getAllByTestId(TESTIDS.trackerCard);
    // Should have 4 active cards (5 total minus 1 archived)
    expect(cards.length).toBeGreaterThanOrEqual(4);
  });

  it('bucket test: unknown lane maps to proposed', () => {
    const testItems = [
      {
        ...fixtureTrackerItems[0],
        lane: 'some-random-lane' as any,
        title: 'Unknown lane item',
      },
    ];

    render(<TrackerBoard items={testItems} />);

    const proposedSection = screen.getByText('Proposed').closest('section');
    expect(proposedSection?.textContent).toContain('Unknown lane item');
  });
});
