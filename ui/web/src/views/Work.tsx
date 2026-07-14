/**
 * Work view — tracker kanban board + backlog panel + form.
 * Binds TrackerBoard, TrackerCard, TrackerForm, BacklogPanel.
 * Reads tracker + backlog from SSE, allows mutations.
 */

import { useEffect, useState } from 'react';
import { useSSE } from '../lib/useSSE';
import { TrackerBoard } from '../components/TrackerBoard';
import { TrackerForm } from '../components/TrackerForm';
import { BacklogPanel } from '../components/BacklogPanel';
import { TESTIDS } from '../test/fixtures';
import type { TrackerItem, AuditBacklog } from '../lib/types';
import '../styles/work.css';

export function Work() {
  const sse = useSSE();
  const [trackerItems, setTrackerItems] = useState<TrackerItem[]>([]);
  const [backlog, setBacklog] = useState<AuditBacklog | null>(null);
  const [showForm, setShowForm] = useState(false);

  useEffect(() => {
    if (sse.tracker?.items) {
      setTrackerItems(sse.tracker.items);
    }
  }, [sse.tracker]);

  useEffect(() => {
    if (sse.backlog) {
      setBacklog(sse.backlog);
    }
  }, [sse.backlog]);

  const handleItemUpdate = (updated: TrackerItem) => {
    setTrackerItems((prev) =>
      prev.map((item) => (item.id === updated.id ? updated : item))
    );
  };

  const handleFormSuccess = () => {
    setShowForm(false);
    // Tracker board will update via SSE
  };

  return (
    <section className="work-view" data-testid={TESTIDS.viewWork} aria-label="Work view">
      <div className="work-container">
        <div className="work-board">
          <div className="board-header">
            <h2>Tracker Kanban</h2>
            <button
              type="button"
              className="add-item-button"
              onClick={() => setShowForm(!showForm)}
              aria-expanded={showForm}
            >
              {showForm ? 'Cancel' : '+ Add Item'}
            </button>
          </div>

          {showForm && (
            <div className="form-container">
              <TrackerForm onSuccess={handleFormSuccess} />
            </div>
          )}

          <TrackerBoard items={trackerItems} onUpdate={handleItemUpdate} />
        </div>

        <aside className="work-sidebar">
          <BacklogPanel backlog={backlog} />
        </aside>
      </div>
    </section>
  );
}
