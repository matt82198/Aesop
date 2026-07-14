/**
 * Activity view — Agent timeline + main-thread messages tail.
 * Read-only observability: shows agent execution spans and orchestrator reasoning.
 */

import Timeline from '../components/Timeline';
import MessagesTail from '../components/MessagesTail';
import { TESTIDS } from '../test/fixtures';
import type { FullState } from '../lib/types';
import styles from './Activity.module.css';

interface Props {
  state: FullState;
}

export default function Activity({ state }: Props) {
  const agents = state.agents || [];
  const messages = state.data.messages || [];

  return (
    <div data-testid={TESTIDS.viewActivity} className={styles.container}>
      <section className={styles.section}>
        <Timeline agents={agents} />
      </section>

      <section className={styles.section}>
        <MessagesTail messages={messages} />
      </section>
    </div>
  );
}
