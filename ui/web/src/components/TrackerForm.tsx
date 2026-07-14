/**
 * TrackerForm — form to create new tracker items.
 * Labeled inputs for title, priority, tags, notes.
 * Submit via api.ts with CSRF.
 * Validation, success/error announced via aria-live.
 */

import { useState } from 'react';
import { TESTIDS } from '../test/fixtures';
import { createTrackerItem } from '../lib/api';

interface TrackerFormProps {
  onSuccess?: () => void;
}

export function TrackerForm({ onSuccess }: TrackerFormProps) {
  const [title, setTitle] = useState('');
  const [priority, setPriority] = useState('P1');
  const [tags, setTags] = useState('');
  const [notes, setNotes] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSuccess(false);

    // Validation
    if (!title.trim()) {
      setError('Title is required');
      return;
    }

    // If validation passes, proceed with async submit
    performSubmit();
  }

  async function performSubmit() {

    const tagArray = tags
      .split(',')
      .map((t) => t.trim())
      .filter((t) => t.length > 0);

    setLoading(true);
    try {
      await createTrackerItem({
        title: title.trim(),
        priority,
        tags: tagArray,
        notes: notes.trim() || undefined,
      });

      setSuccess(true);
      setTitle('');
      setPriority('P1');
      setTags('');
      setNotes('');
      onSuccess?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create item');
    } finally {
      setLoading(false);
    }
  }

  return (
    <form className="tracker-form" data-testid={TESTIDS.trackerForm} onSubmit={handleSubmit}>
      <div className="form-group">
        <label htmlFor="tracker-title">Title</label>
        <input
          id="tracker-title"
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Enter item title"
          disabled={loading}
          required
          data-testid={TESTIDS.trackerFormTitle}
        />
      </div>

      <div className="form-group">
        <label htmlFor="tracker-priority">Priority</label>
        <select
          id="tracker-priority"
          value={priority}
          onChange={(e) => setPriority(e.target.value)}
          disabled={loading}
        >
          <option value="P0">P0 (Critical)</option>
          <option value="P1">P1 (High)</option>
          <option value="P2">P2 (Medium)</option>
        </select>
      </div>

      <div className="form-group">
        <label htmlFor="tracker-tags">Tags (comma-separated)</label>
        <input
          id="tracker-tags"
          type="text"
          value={tags}
          onChange={(e) => setTags(e.target.value)}
          placeholder="e.g., ui, wave-14, critical"
          disabled={loading}
        />
      </div>

      <div className="form-group">
        <label htmlFor="tracker-notes">Notes</label>
        <textarea
          id="tracker-notes"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="Optional notes"
          rows={3}
          disabled={loading}
        />
      </div>

      <button
        type="submit"
        disabled={loading}
        data-testid={TESTIDS.trackerFormSubmit}
      >
        {loading ? 'Creating...' : 'Create Item'}
      </button>

      {error && (
        <div className="form-error" role="alert" aria-live="assertive">
          {error}
        </div>
      )}

      {success && (
        <div className="form-success" role="status" aria-live="polite">
          Item created successfully!
        </div>
      )}
    </form>
  );
}
