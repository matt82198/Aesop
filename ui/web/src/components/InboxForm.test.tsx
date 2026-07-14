import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { userEvent } from '@testing-library/user-event';
import { InboxForm } from './InboxForm';
import { TESTIDS } from '../test/fixtures';
import * as api from '../lib/api';

vi.mock('../lib/api', () => ({
  submitInbox: vi.fn(),
}));

describe('InboxForm', () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it('renders form with input and submit button', () => {
    render(<InboxForm />);

    expect(screen.getByTestId(TESTIDS.inboxForm)).toBeInTheDocument();
    expect(screen.getByTestId(TESTIDS.inboxInput)).toBeInTheDocument();
    expect(screen.getByTestId(TESTIDS.inboxSubmit)).toBeInTheDocument();
  });

  it('displays placeholder text', () => {
    render(<InboxForm />);

    const input = screen.getByTestId(TESTIDS.inboxInput) as HTMLInputElement;
    expect(input).toHaveAttribute('placeholder', 'Add a task or note…');
  });

  it('disables submit button when input is empty', () => {
    render(<InboxForm />);

    const submitButton = screen.getByTestId(TESTIDS.inboxSubmit) as HTMLButtonElement;
    expect(submitButton).toBeDisabled();
  });

  it('enables submit button when input has text', async () => {
    const user = userEvent.setup();
    render(<InboxForm />);

    const input = screen.getByTestId(TESTIDS.inboxInput);
    await user.type(input, 'Test message');

    const submitButton = screen.getByTestId(TESTIDS.inboxSubmit) as HTMLButtonElement;
    expect(submitButton).not.toBeDisabled();
  });

  it('submits form on button click', async () => {
    const user = userEvent.setup();
    const mockSubmit = vi.mocked(api.submitInbox);
    mockSubmit.mockResolvedValueOnce({ ok: true });

    render(<InboxForm />);

    const input = screen.getByTestId(TESTIDS.inboxInput);
    await user.type(input, 'Test message');

    const submitButton = screen.getByTestId(TESTIDS.inboxSubmit);
    await user.click(submitButton);

    await waitFor(() => {
      expect(mockSubmit).toHaveBeenCalledWith('Test message');
    });
  });

  it('clears input on successful submission', async () => {
    const user = userEvent.setup();
    const mockSubmit = vi.mocked(api.submitInbox);
    mockSubmit.mockResolvedValueOnce({ ok: true });

    render(<InboxForm />);

    const input = screen.getByTestId(TESTIDS.inboxInput) as HTMLInputElement;
    await user.type(input, 'Test message');

    const submitButton = screen.getByTestId(TESTIDS.inboxSubmit);
    await user.click(submitButton);

    await waitFor(() => {
      expect(input.value).toBe('');
    });
  });

  it('displays success message after submission', async () => {
    const user = userEvent.setup();
    const mockSubmit = vi.mocked(api.submitInbox);
    mockSubmit.mockResolvedValueOnce({ ok: true });

    render(<InboxForm />);

    const input = screen.getByTestId(TESTIDS.inboxInput);
    await user.type(input, 'Test message');

    const submitButton = screen.getByTestId(TESTIDS.inboxSubmit);
    await user.click(submitButton);

    await waitFor(() => {
      expect(screen.getByText('Message submitted!')).toBeInTheDocument();
    });
  });

  it('handles submission error', async () => {
    const user = userEvent.setup();
    const mockSubmit = vi.mocked(api.submitInbox);
    mockSubmit.mockRejectedValueOnce(new Error('Network error'));

    render(<InboxForm />);

    const input = screen.getByTestId(TESTIDS.inboxInput);
    await user.type(input, 'Test message');

    const submitButton = screen.getByTestId(TESTIDS.inboxSubmit);
    await user.click(submitButton);

    await waitFor(() => {
      expect(screen.getByText(/Error: Network error/)).toBeInTheDocument();
    });
  });

  it('disables input while submitting', async () => {
    const user = userEvent.setup();
    const mockSubmit = vi.mocked(api.submitInbox);
    mockSubmit.mockImplementationOnce(
      () =>
        new Promise((resolve) =>
          setTimeout(() => resolve({ ok: true }), 100)
        )
    );

    render(<InboxForm />);

    const input = screen.getByTestId(TESTIDS.inboxInput) as HTMLInputElement;
    await user.type(input, 'Test message');

    const submitButton = screen.getByTestId(TESTIDS.inboxSubmit);
    await user.click(submitButton);

    expect(input).toBeDisabled();

    await waitFor(() => {
      expect(input).not.toBeDisabled();
    });
  });

  it('calls onSubmitSuccess callback after successful submission', async () => {
    const user = userEvent.setup();
    const mockSubmit = vi.mocked(api.submitInbox);
    const mockCallback = vi.fn();
    mockSubmit.mockResolvedValueOnce({ ok: true });

    render(<InboxForm onSubmitSuccess={mockCallback} />);

    const input = screen.getByTestId(TESTIDS.inboxInput);
    await user.type(input, 'Test message');

    const submitButton = screen.getByTestId(TESTIDS.inboxSubmit);
    await user.click(submitButton);

    await waitFor(() => {
      expect(mockCallback).toHaveBeenCalled();
    });
  });

  it('has proper accessibility attributes', () => {
    render(<InboxForm />);

    const input = screen.getByTestId(TESTIDS.inboxInput);
    expect(input).toHaveAttribute('id', 'inbox-input');

    const label = screen.getByLabelText('Message');
    expect(label).toBe(input);
  });

  it('submits on Enter key in input', async () => {
    const user = userEvent.setup();
    const mockSubmit = vi.mocked(api.submitInbox);
    mockSubmit.mockResolvedValueOnce({ ok: true });

    render(<InboxForm />);

    const input = screen.getByTestId(TESTIDS.inboxInput);
    await user.type(input, 'Test message{Enter}');

    await waitFor(() => {
      expect(mockSubmit).toHaveBeenCalledWith('Test message');
    });
  });

  it('trims whitespace from submission', async () => {
    const user = userEvent.setup();
    const mockSubmit = vi.mocked(api.submitInbox);
    mockSubmit.mockResolvedValueOnce({ ok: true });

    render(<InboxForm />);

    const input = screen.getByTestId(TESTIDS.inboxInput);
    await user.type(input, '  Test message  ');

    const submitButton = screen.getByTestId(TESTIDS.inboxSubmit);
    await user.click(submitButton);

    await waitFor(() => {
      expect(mockSubmit).toHaveBeenCalledWith('Test message');
    });
  });
});
