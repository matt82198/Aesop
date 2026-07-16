import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { TrackerCard } from './TrackerCard';
import { fixtureTrackerItems } from '../test/fixtures';
import * as api from '../lib/api';

vi.mock('../lib/api');

afterEach(() => {
  vi.clearAllMocks();
});

describe('TrackerCard', () => {
  it('renders title, priority chip, and tags', () => {
    const item = fixtureTrackerItems[0]; // P0 in-progress item
    render(<TrackerCard item={item} />);

    expect(screen.getByText(item.title)).toBeInTheDocument();
    expect(screen.getByText(item.priority)).toBeInTheDocument();
    expect(screen.getByText('ui')).toBeInTheDocument();
    expect(screen.getByText('wave-14')).toBeInTheDocument();
  });

  it('shows expand/collapse button and toggles details on click', async () => {
    const item = fixtureTrackerItems[0];
    render(<TrackerCard item={item} />);

    const expandButton = screen.getByRole('button', { name: /expand/i });
    expect(expandButton).toHaveAttribute('aria-expanded', 'false');

    // Initially details should not be visible
    expect(screen.queryByText(/Created/)).not.toBeInTheDocument();

    fireEvent.click(expandButton);
    await waitFor(() => {
      expect(expandButton).toHaveAttribute('aria-expanded', 'true');
    });

    // Now details should be visible
    expect(screen.getByText(/Created/)).toBeInTheDocument();
  });

  it('displays notes in expanded state', () => {
    const item = fixtureTrackerItems[0];
    render(<TrackerCard item={item} />);

    // Expand
    fireEvent.click(screen.getByRole('button', { name: /expand/i }));

    expect(screen.getByText(item.notes!)).toBeInTheDocument();
  });

  it('displays created and completed timestamps when expanded', () => {
    const item = fixtureTrackerItems[1]; // This one has completed_at
    render(<TrackerCard item={item} />);

    fireEvent.click(screen.getByRole('button', { name: /expand/i }));

    const times = screen.getAllByRole('time');
    expect(times.length).toBeGreaterThanOrEqual(2); // created + completed
  });

  it('renders pr_link as inert text when URL is malicious (javascript:)', async () => {
    const item = fixtureTrackerItems[4]; // The hostile javascript: pr_link
    expect(item.pr_link).toBe('javascript:alert(1)');

    render(<TrackerCard item={item} />);
    fireEvent.click(screen.getByRole('button', { name: /expand/i }));

    await waitFor(() => {
      // Should render as <code class="pr-link-inert"> not as <a href>
      const code = screen.getByText('javascript:alert(1)');
      expect(code.tagName).toBe('CODE');
      expect(code).toHaveClass('pr-link-inert');
    });

    // Assert no <a> element exists
    expect(screen.queryByRole('link', { name: 'javascript:alert(1)' })).not.toBeInTheDocument();
  });

  it('renders pr_link as clickable anchor when URL is https://', async () => {
    const item = {
      ...fixtureTrackerItems[0],
      pr_link: 'https://example.com/pull/123',
    };

    render(<TrackerCard item={item} />);
    fireEvent.click(screen.getByRole('button', { name: /expand/i }));

    await waitFor(() => {
      const link = screen.getByRole('link', { name: /example.com/ });
      expect(link).toHaveAttribute('href', item.pr_link);
      expect(link).toHaveAttribute('target', '_blank');
    });
  });

  it('renders action buttons for the tracker item', () => {
    const item = fixtureTrackerItems[0];

    render(<TrackerCard item={item} />);

    // Find all buttons
    const buttons = screen.getAllByRole('button');
    const actionButtons = buttons.filter((b) => {
      const text = b.textContent?.trim() || '';
      return text === 'Claim' || text === 'Done' || text === 'Archive';
    });

    // Should have at least 3 action buttons
    expect(actionButtons.length).toBeGreaterThanOrEqual(3);
  });

  it('Done button updates status to done', async () => {
    const item = fixtureTrackerItems[0];
    const mockUpdate = vi.fn();
    const updated = { ...item, status: 'done' as const, lane: 'done' as const };

    vi.mocked(api.updateTrackerItem).mockResolvedValue(updated);

    render(<TrackerCard item={item} onUpdate={mockUpdate} />);

    // Find the Done button within the actions section
    const buttons = screen.getAllByRole('button');
    const doneButton = buttons.find((b) => b.textContent === 'Done');
    expect(doneButton).toBeDefined();

    fireEvent.click(doneButton!);

    await waitFor(() => {
      expect(api.updateTrackerItem).toHaveBeenCalledWith(item.id, {
        lane: 'done',
        status: 'done',
      });
    });
  });

  it('Archive button updates status to archived', async () => {
    const item = fixtureTrackerItems[0];
    const mockUpdate = vi.fn();
    const updated = { ...item, status: 'archived' as const, lane: 'done' as const };

    vi.mocked(api.updateTrackerItem).mockResolvedValue(updated);

    render(<TrackerCard item={item} onUpdate={mockUpdate} />);

    const archiveButton = screen.getByRole('button', { name: /Archive/ });
    fireEvent.click(archiveButton);

    await waitFor(() => {
      expect(api.updateTrackerItem).toHaveBeenCalledWith(item.id, {
        status: 'archived',
        lane: 'done',
      });
    });
  });

  it('renders all action buttons', () => {
    const item = fixtureTrackerItems[0];

    render(<TrackerCard item={item} />);

    // Verify all action buttons are present
    const buttons = screen.getAllByRole('button');
    const claimButton = buttons.find((b) => b.textContent?.trim() === 'Claim');
    const doneButton = buttons.find((b) => b.textContent?.trim() === 'Done');
    const archiveButton = buttons.find((b) => b.textContent?.trim() === 'Archive');

    expect(claimButton).toBeDefined();
    expect(doneButton).toBeDefined();
    expect(archiveButton).toBeDefined();
  });

  it('buttons are disabled when status already matches action', () => {
    const item = { ...fixtureTrackerItems[0], status: 'in-progress' as const };
    render(<TrackerCard item={item} />);

    const claimButton = screen.getByRole('button', { name: /Claim/ });
    expect(claimButton).toBeDisabled();
  });
});
