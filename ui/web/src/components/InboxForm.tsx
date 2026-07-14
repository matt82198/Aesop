/**
 * InboxForm — Quick inbox submit form with aria-live announcement.
 *
 * D5: real <form> and <button> elements, labeled input, success/error
 * announced to an aria-live region.
 */

import { useState, useRef, useCallback } from 'react';
import { submitInbox } from '../lib/api';
import { TESTIDS } from '../test/fixtures';
import './InboxForm.css';

interface InboxFormProps {
  onSubmitSuccess?: () => void;
}

export function InboxForm({ onSubmitSuccess }: InboxFormProps) {
  const [input, setInput] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const liveRegionRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();

      if (!input.trim()) {
        setError('Please enter a message');
        return;
      }

      setIsSubmitting(true);
      setError(null);
      setSuccess(false);

      try {
        await submitInbox(input.trim());
        setInput('');
        setSuccess(true);
        // Announce to live region
        if (liveRegionRef.current) {
          liveRegionRef.current.textContent = `Message submitted: "${input.trim()}"`;
        }
        onSubmitSuccess?.();
        // Clear success message after 3 seconds
        setTimeout(() => setSuccess(false), 3000);
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Failed to submit';
        setError(message);
        // Announce error to live region
        if (liveRegionRef.current) {
          liveRegionRef.current.textContent = `Error: ${message}`;
        }
      } finally {
        setIsSubmitting(false);
      }
    },
    [input, onSubmitSuccess]
  );

  return (
    <section className="inbox-form" data-testid={TESTIDS.inboxForm}>
      <h2>Quick Inbox</h2>
      <form onSubmit={handleSubmit} className="inbox-form__form">
        <div className="inbox-form__group">
          <label htmlFor="inbox-input" className="sr-only">
            Message
          </label>
          <input
            ref={inputRef}
            id="inbox-input"
            type="text"
            className="inbox-form__input"
            data-testid={TESTIDS.inboxInput}
            placeholder="Add a task or note…"
            value={input}
            onChange={(e) => setInput(e.currentTarget.value)}
            disabled={isSubmitting}
            aria-describedby={error ? 'inbox-error' : undefined}
          />
          <button
            type="submit"
            className="inbox-form__submit"
            data-testid={TESTIDS.inboxSubmit}
            disabled={isSubmitting || !input.trim()}
            aria-label={isSubmitting ? 'Submitting…' : 'Submit message'}
          >
            {isSubmitting ? 'Submitting…' : 'Submit'}
          </button>
        </div>

        {error && (
          <div className="inbox-form__error" id="inbox-error">
            {error}
          </div>
        )}

        {success && (
          <div className="inbox-form__success">
            Message submitted!
          </div>
        )}
      </form>

      <div
        ref={liveRegionRef}
        className="sr-only"
        role="status"
        aria-live="polite"
        aria-atomic="true"
      />
    </section>
  );
}
