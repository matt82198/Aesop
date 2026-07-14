/**
 * TrackerBoard — kanban-style layout with 4 lanes + archived summary.
 * Lane bucketing: proposed/ranked/in-progress/done.
 * Unknown lanes -> proposed. Empty lanes compact.
 * Lane counts with accessible labels and health badges.
 */

import { TESTIDS } from '../test/fixtures';
import type { TrackerItem } from '../lib/types';
import { TrackerCard } from './TrackerCard';

interface TrackerBoardProps {
  items: TrackerItem[];
  onUpdate?: (item: TrackerItem) => void;
}

const LANE_ORDER = ['proposed', 'ranked', 'in-progress', 'done'] as const;
type Lane = (typeof LANE_ORDER)[number];

function getLaneLabel(lane: Lane): string {
  return {
    proposed: 'Proposed',
    ranked: 'Ranked',
    'in-progress': 'In Progress',
    done: 'Done',
  }[lane];
}

function normalizeLane(lane: string | undefined): Lane {
  const normalized = lane?.toLowerCase();
  if (LANE_ORDER.includes(normalized as Lane)) {
    return normalized as Lane;
  }
  return 'proposed'; // unknown lane -> proposed
}

export function TrackerBoard({ items, onUpdate }: TrackerBoardProps) {
  // Separate active items from archived
  const activeItems = items.filter((item) => item.status !== 'archived');
  const archivedItems = items.filter((item) => item.status === 'archived');

  // Bucket active items by lane
  const laneMap = new Map<Lane, TrackerItem[]>();
  LANE_ORDER.forEach((lane) => laneMap.set(lane, []));

  activeItems.forEach((item) => {
    const lane = normalizeLane(item.lane);
    laneMap.get(lane)?.push(item);
  });

  // Render lanes
  const renderedLanes = LANE_ORDER.map((lane) => {
    const items = laneMap.get(lane) || [];

    // Calculate health badge info (done/total where derivable)
    let badgeText = `${items.length} items`;
    if (lane === 'done') {
      badgeText = `${items.length}/${items.length} done`;
    } else if (items.length > 0) {
      const doneCount = items.filter((item) => item.status === 'done').length;
      if (doneCount > 0) {
        badgeText = `${doneCount}/${items.length} done`;
      }
    }

    return (
      <section key={lane} className="tracker-lane" data-testid={TESTIDS.trackerLane}>
        <h2 className="lane-header">
          {getLaneLabel(lane)}
          <span
            className={`lane-badge ${items.length === 0 ? 'lane-badge--empty' : 'lane-badge--active'}`}
            aria-label={`${badgeText} in ${getLaneLabel(lane)}`}
          >
            {badgeText}
          </span>
        </h2>
        <div className="lane-content">
          {items.length === 0 ? (
            <p className="lane-empty">No items</p>
          ) : (
            items.map((item) => <TrackerCard key={item.id} item={item} onUpdate={onUpdate} />)
          )}
        </div>
      </section>
    );
  });

  return (
    <div className="tracker-board" data-testid={TESTIDS.trackerBoard}>
      <div className="lanes-container">{renderedLanes}</div>

      {archivedItems.length > 0 && (
        <section className="archived-summary">
          <h3>Archived ({archivedItems.length})</h3>
          <ul className="archived-list">
            {archivedItems.map((item) => (
              <li key={item.id} className="archived-item">
                <span className="archived-title">{item.title}</span>
                <span className="archived-priority">{item.priority}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
