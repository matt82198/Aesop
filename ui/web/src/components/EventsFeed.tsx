/**
 * EventsFeed — FLEET-BACKUP.log tail (recent events).
 */

import { TESTIDS } from '../test/fixtures';
import './EventsFeed.css';

interface EventsFeedProps {
  events: string[] | null;
}

export function EventsFeed({ events }: EventsFeedProps) {
  const hasEvents = events && events.length > 0;

  return (
    <section className="events-feed" data-testid={TESTIDS.eventsFeed}>
      <h2>Recent Events</h2>
      {!hasEvents ? (
        <p className="empty-state">No events.</p>
      ) : (
        <ul className="events-feed__list">
          {events.map((event, idx) => (
            <li key={idx} className="events-feed__item">
              <code>{event}</code>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
