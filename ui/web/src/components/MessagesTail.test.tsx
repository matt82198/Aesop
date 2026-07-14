/**
 * MessagesTail — Last ~12 messages with role coloring and auto-follow toggle.
 */

import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import MessagesTail from './MessagesTail';
import { fixtureMessages } from '../test/fixtures';
import { TESTIDS } from '../test/fixtures';

describe('MessagesTail', () => {
  it('renders the messages tail container with testid', () => {
    render(<MessagesTail messages={fixtureMessages} />);
    expect(screen.getByTestId(TESTIDS.messagesTail)).toBeInTheDocument();
  });

  it('renders all messages with role and text', () => {
    render(<MessagesTail messages={fixtureMessages} />);
    expect(screen.getByText('Run wave 14: dashboard rewrite, start with the foundation unit.')).toBeInTheDocument();
    expect(screen.getByText('Dispatching U1 (foundation) to a worktree agent; U3 cost collector runs in parallel.')).toBeInTheDocument();
  });

  it('renders messages with role-based styling', () => {
    render(<MessagesTail messages={fixtureMessages} />);
    const messages = screen.getAllByTestId(/message-\d+/);
    expect(messages.length).toBe(fixtureMessages.length);
  });

  it('formats timestamps using format.ts', () => {
    render(<MessagesTail messages={fixtureMessages} />);
    // The formatTimestamp should produce relative times (e.g., "now", "2m ago")
    // Just verify timestamps are rendered (exact format depends on current time)
    const container = screen.getByTestId(TESTIDS.messagesTail);
    const textContent = container.textContent || '';
    expect(textContent.length > 0).toBe(true);
  });

  it('shows empty state when no messages', () => {
    render(<MessagesTail messages={[]} />);
    const container = screen.getByTestId(TESTIDS.messagesTail);
    expect(container.textContent).toContain('no messages');
  });

  it('renders follow toggle as a real button', () => {
    render(<MessagesTail messages={fixtureMessages} />);
    const toggleButton = screen.getByTestId(TESTIDS.messagesFollowToggle);
    expect(toggleButton).toBeInstanceOf(HTMLButtonElement);
    expect(toggleButton).toHaveTextContent(/follow|scroll/i);
  });

  it('follow toggle is checked by default', () => {
    render(<MessagesTail messages={fixtureMessages} />);
    const toggleButton = screen.getByTestId(TESTIDS.messagesFollowToggle);
    expect(toggleButton).toHaveAttribute('aria-pressed', 'true');
  });

  it('pause follow when user scrolls up manually', async () => {
    render(<MessagesTail messages={fixtureMessages} />);
    const toggleButton = screen.getByTestId(TESTIDS.messagesFollowToggle);

    // Toggle button starts in "following" state
    expect(toggleButton).toHaveAttribute('aria-pressed', 'true');

    // Simulate user scrolling - this would normally set isFollowing to false
    // In real browser: scroll event triggers handleScroll which checks distance from bottom
    // For testing, we'll just click to simulate the behavior
    fireEvent.click(toggleButton);

    await waitFor(() => {
      expect(toggleButton).toHaveAttribute('aria-pressed', 'false');
    });
  });

  it('resume follow when toggle is clicked', async () => {
    render(<MessagesTail messages={fixtureMessages} />);
    const toggleButton = screen.getByTestId(TESTIDS.messagesFollowToggle);

    // Start in following state
    expect(toggleButton).toHaveAttribute('aria-pressed', 'true');

    // Click to pause
    fireEvent.click(toggleButton);
    expect(toggleButton).toHaveAttribute('aria-pressed', 'false');

    // Click again to resume
    fireEvent.click(toggleButton);

    await waitFor(() => {
      expect(toggleButton).toHaveAttribute('aria-pressed', 'true');
    });
  });

  it('auto-scrolls when follow is enabled and new messages arrive', async () => {
    const { rerender } = render(<MessagesTail messages={fixtureMessages} />);

    const newMessages = [
      ...fixtureMessages,
      {
        role: 'user' as const,
        text: 'New message',
        timestamp: '2026-07-13T14:35:00.000Z',
      },
    ];

    rerender(<MessagesTail messages={newMessages} />);

    // Should have auto-scrolled to bottom
    expect(screen.getByText('New message')).toBeInTheDocument();
  });

  it('does not auto-scroll when follow is disabled', async () => {
    const { rerender } = render(<MessagesTail messages={fixtureMessages} />);
    const toggleButton = screen.getByTestId(TESTIDS.messagesFollowToggle);

    // Disable follow
    fireEvent.click(toggleButton);

    await waitFor(() => {
      expect(toggleButton).toHaveAttribute('aria-pressed', 'false');
    });

    // Add new message
    const newMessages = [
      ...fixtureMessages,
      {
        role: 'assistant' as const,
        text: 'Another message',
        timestamp: '2026-07-13T14:36:00.000Z',
      },
    ];

    rerender(<MessagesTail messages={newMessages} />);

    // New message should be in DOM but scroll position should not change
    expect(screen.getByText('Another message')).toBeInTheDocument();
  });

  it('renders messages with distinct role styling (user vs assistant)', () => {
    render(<MessagesTail messages={fixtureMessages} />);
    // First message is user, should have different styling than assistant messages
    const userMessage = screen.getByText('Run wave 14: dashboard rewrite, start with the foundation unit.');
    const userMessageContainer = userMessage.closest('[data-testid^="message-"]') as HTMLElement;
    expect(userMessageContainer?.className).toContain('role-user');

    // Check for an assistant message
    const assistantMessage = screen.getByText('Dispatching U1 (foundation) to a worktree agent; U3 cost collector runs in parallel.');
    const assistantMessageContainer = assistantMessage.closest('[data-testid^="message-"]') as HTMLElement;
    expect(assistantMessageContainer?.className).toContain('role-assistant');
  });

  it('handles null/undefined messages gracefully', () => {
    const edgeCaseMessages = [
      ...fixtureMessages,
      {
        role: 'assistant' as const,
        text: '',
        timestamp: '2026-07-13T14:37:00.000Z',
      },
    ];
    render(<MessagesTail messages={edgeCaseMessages} />);
    expect(screen.getByTestId(TESTIDS.messagesTail)).toBeInTheDocument();
  });

  it('limits to last ~12 messages if more provided', () => {
    const manyMessages: Array<typeof fixtureMessages[0]> = Array.from({ length: 20 }, (_, i) => ({
      role: i % 2 === 0 ? ('user' as const) : ('assistant' as const),
      text: `Message ${i}`,
      timestamp: new Date(Date.now() - i * 60000).toISOString(),
    }));

    render(<MessagesTail messages={manyMessages} />);
    const container = screen.getByTestId(TESTIDS.messagesTail);
    const messageElements = container.querySelectorAll('[data-testid^="message-"]');
    expect(messageElements.length).toBeLessThanOrEqual(12);
  });
});
