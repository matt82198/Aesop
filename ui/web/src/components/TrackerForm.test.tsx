import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { TrackerForm } from './TrackerForm';
import { fixtureTrackerItems } from '../test/fixtures';
import * as api from '../lib/api';

vi.mock('../lib/api');

afterEach(() => {
  vi.clearAllMocks();
});

describe('TrackerForm', () => {
  it('renders form with labeled inputs', () => {
    render(<TrackerForm />);

    expect(screen.getByLabelText('Title')).toBeInTheDocument();
    expect(screen.getByLabelText('Priority')).toBeInTheDocument();
    expect(screen.getByLabelText(/Tags/)).toBeInTheDocument();
    expect(screen.getByLabelText('Notes')).toBeInTheDocument();
  });

  it('title field is required and form does not submit without it', async () => {
    const newItem = fixtureTrackerItems[0];
    vi.mocked(api.createTrackerItem).mockResolvedValue(newItem);

    render(<TrackerForm />);

    const submitButton = screen.getByRole('button', { name: /Create Item/ });
    fireEvent.click(submitButton);

    // createTrackerItem should NOT be called since title is empty
    await new Promise((resolve) => setTimeout(resolve, 100));
    expect(api.createTrackerItem).not.toHaveBeenCalled();
  });

  it('calls createTrackerItem with form data and announces success', async () => {
    const mockSuccess = vi.fn();
    const newItem = fixtureTrackerItems[0];

    vi.mocked(api.createTrackerItem).mockResolvedValue(newItem);

    render(<TrackerForm onSuccess={mockSuccess} />);

    fireEvent.change(screen.getByLabelText('Title'), { target: { value: 'Test item' } });
    fireEvent.change(screen.getByLabelText('Priority'), { target: { value: 'P0' } });
    fireEvent.change(screen.getByLabelText(/Tags/), { target: { value: 'tag1, tag2' } });
    fireEvent.change(screen.getByLabelText('Notes'), { target: { value: 'Test notes' } });

    const submitButton = screen.getByRole('button', { name: /Create Item/ });
    fireEvent.click(submitButton);

    await waitFor(() => {
      expect(api.createTrackerItem).toHaveBeenCalledWith({
        title: 'Test item',
        priority: 'P0',
        tags: ['tag1', 'tag2'],
        notes: 'Test notes',
      });
      expect(mockSuccess).toHaveBeenCalled();
    });

    // Success message should be announced
    const successMsg = screen.getByText('Item created successfully!');
    expect(successMsg).toHaveAttribute('role', 'status');
    expect(successMsg).toHaveAttribute('aria-live', 'polite');
  });

  it('parses comma-separated tags correctly', async () => {
    const newItem = fixtureTrackerItems[0];
    vi.mocked(api.createTrackerItem).mockResolvedValue(newItem);

    render(<TrackerForm />);

    fireEvent.change(screen.getByLabelText('Title'), { target: { value: 'Test' } });
    fireEvent.change(screen.getByLabelText(/Tags/), { target: { value: '  ui , wave-14 , critical  ' } });

    fireEvent.click(screen.getByRole('button', { name: /Create Item/ }));

    await waitFor(() => {
      expect(api.createTrackerItem).toHaveBeenCalledWith(
        expect.objectContaining({
          tags: ['ui', 'wave-14', 'critical'],
        })
      );
    });
  });

  it('trims whitespace from title and notes', async () => {
    const newItem = fixtureTrackerItems[0];
    vi.mocked(api.createTrackerItem).mockResolvedValue(newItem);

    render(<TrackerForm />);

    fireEvent.change(screen.getByLabelText('Title'), { target: { value: '  Test item  ' } });
    fireEvent.change(screen.getByLabelText('Notes'), { target: { value: '  Some notes  ' } });

    fireEvent.click(screen.getByRole('button', { name: /Create Item/ }));

    await waitFor(() => {
      expect(api.createTrackerItem).toHaveBeenCalledWith(
        expect.objectContaining({
          title: 'Test item',
          notes: 'Some notes',
        })
      );
    });
  });

  it('clears form after successful submission', async () => {
    const newItem = fixtureTrackerItems[0];
    vi.mocked(api.createTrackerItem).mockResolvedValue(newItem);

    render(<TrackerForm />);

    const titleInput = screen.getByLabelText('Title') as HTMLInputElement;
    fireEvent.change(titleInput, { target: { value: 'Test item' } });
    fireEvent.change(screen.getByLabelText('Priority'), { target: { value: 'P0' } });
    fireEvent.change(screen.getByLabelText(/Tags/), { target: { value: 'tag1' } });

    fireEvent.click(screen.getByRole('button', { name: /Create Item/ }));

    await waitFor(() => {
      expect(titleInput.value).toBe('');
    });
  });

  it('announces errors via aria-live=assertive', async () => {
    vi.mocked(api.createTrackerItem).mockRejectedValue(new Error('Network error'));

    render(<TrackerForm />);

    fireEvent.change(screen.getByLabelText('Title'), { target: { value: 'Test' } });
    fireEvent.click(screen.getByRole('button', { name: /Create Item/ }));

    await waitFor(() => {
      const errorMsg = screen.getByText('Network error');
      expect(errorMsg).toHaveAttribute('role', 'alert');
      expect(errorMsg).toHaveAttribute('aria-live', 'assertive');
    });
  });

  it('disables inputs and button while loading', async () => {
    vi.mocked(api.createTrackerItem).mockImplementation(
      () => new Promise((resolve) => setTimeout(() => resolve(fixtureTrackerItems[0]), 100))
    );

    render(<TrackerForm />);

    fireEvent.change(screen.getByLabelText('Title'), { target: { value: 'Test' } });
    const submitButton = screen.getByRole('button', { name: /Create Item/ });

    fireEvent.click(submitButton);

    expect(submitButton).toBeDisabled();
    expect(screen.getByLabelText('Title')).toBeDisabled();

    await waitFor(() => {
      expect(submitButton).not.toBeDisabled();
    });
  });

  it('default priority is P1', () => {
    render(<TrackerForm />);

    const prioritySelect = screen.getByLabelText('Priority') as HTMLSelectElement;
    expect(prioritySelect.value).toBe('P1');
  });

  it('omits notes if empty', async () => {
    const newItem = fixtureTrackerItems[0];
    vi.mocked(api.createTrackerItem).mockResolvedValue(newItem);

    render(<TrackerForm />);

    fireEvent.change(screen.getByLabelText('Title'), { target: { value: 'Test' } });
    // Don't set notes

    fireEvent.click(screen.getByRole('button', { name: /Create Item/ }));

    await waitFor(() => {
      expect(api.createTrackerItem).toHaveBeenCalledWith(
        expect.not.objectContaining({
          notes: '',
        })
      );
    });
  });
});
