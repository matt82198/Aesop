import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { EventsFeed } from './EventsFeed';
import { fixtureEvents, TESTIDS } from '../test/fixtures';

describe('EventsFeed', () => {
  it('renders events list', () => {
    render(<EventsFeed events={fixtureEvents} />);

    expect(screen.getByTestId(TESTIDS.eventsFeed)).toBeInTheDocument();
    fixtureEvents.forEach((event) => {
      expect(screen.getByText(event)).toBeInTheDocument();
    });
  });

  it('renders empty state when no events', () => {
    render(<EventsFeed events={[]} />);

    expect(screen.getByText('No events.')).toBeInTheDocument();
  });

  it('renders empty state when events is null', () => {
    render(<EventsFeed events={null} />);

    expect(screen.getByText('No events.')).toBeInTheDocument();
  });

  it('displays events in monospace font', () => {
    render(<EventsFeed events={fixtureEvents} />);

    const codeElements = screen.getAllByText(/BACKUP|SCAN|PUSH/);
    codeElements.forEach((el) => {
      expect(el.tagName).toBe('CODE');
    });
  });
});
