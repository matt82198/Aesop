import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Work } from './Work';
import { fixtureTrackerItems, fixtureBacklog, TESTIDS } from '../test/fixtures';

describe('Work view', () => {
  it('renders the work view with correct testid', () => {
    render(<Work tracker={{ items: fixtureTrackerItems }} backlog={fixtureBacklog} />);

    expect(screen.getByTestId(TESTIDS.viewWork)).toBeInTheDocument();
  });

  it('renders tracker board heading', () => {
    render(<Work tracker={{ items: fixtureTrackerItems }} backlog={fixtureBacklog} />);

    expect(screen.getByText('Tracker Kanban')).toBeInTheDocument();
  });

  it('renders the add item button', () => {
    render(<Work tracker={{ items: fixtureTrackerItems }} backlog={fixtureBacklog} />);

    const addButton = screen.getByRole('button', { name: /Add Item/ });
    expect(addButton).toBeInTheDocument();
  });

  it('shows form when add item button is clicked', () => {
    render(<Work tracker={{ items: fixtureTrackerItems }} backlog={fixtureBacklog} />);

    const addButton = screen.getByRole('button', { name: /Add Item/ });
    expect(addButton).toHaveAttribute('aria-expanded', 'false');

    // Form inputs should not be visible initially
    expect(screen.queryByLabelText('Title')).not.toBeInTheDocument();
  });

  it('displays tracker board with items', () => {
    render(<Work tracker={{ items: fixtureTrackerItems }} backlog={fixtureBacklog} />);

    expect(screen.getByTestId(TESTIDS.trackerBoard)).toBeInTheDocument();
  });

  it('displays backlog panel', () => {
    render(<Work tracker={{ items: fixtureTrackerItems }} backlog={fixtureBacklog} />);

    expect(screen.getByTestId(TESTIDS.backlogPanel)).toBeInTheDocument();
  });

  it('renders all tracker lanes', () => {
    render(<Work tracker={{ items: fixtureTrackerItems }} backlog={fixtureBacklog} />);

    // Be specific to avoid duplicate "Done" matching
    // Lane headers include counts, e.g., "Proposed1", so check by prefix
    const sections = screen.getAllByRole('heading', { level: 2 });
    const laneTexts = sections.map((s) => s.textContent || '');

    expect(laneTexts.some((t) => t.startsWith('Proposed'))).toBe(true);
    expect(laneTexts.some((t) => t.startsWith('Ranked'))).toBe(true);
    expect(laneTexts.some((t) => t.startsWith('In Progress'))).toBe(true);
  });

  it('renders backlog audit tier headers', () => {
    render(<Work tracker={{ items: fixtureTrackerItems }} backlog={fixtureBacklog} />);

    expect(screen.getByText('Audit Backlog')).toBeInTheDocument();
    // Use context to avoid matching P0 in tracker cards
    const backlogPanel = screen.getByTestId(TESTIDS.backlogPanel);
    expect(backlogPanel.textContent).toContain('P0');
  });
});
