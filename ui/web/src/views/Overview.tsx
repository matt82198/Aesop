/**
 * Overview view — main dashboard combining all overview components.
 *
 * Layout:
 * - Top: AgentsPanel (full width)
 * - Middle row: AlertsPanel | EventsFeed | ReposPanel
 * - Bottom: InboxForm
 *
 * Props passed from App.tsx via SSE state.
 */

import type { Agent, Alert } from '../lib/types';
import { AgentsPanel } from '../components/AgentsPanel';
import { AlertsPanel } from '../components/AlertsPanel';
import { EventsFeed } from '../components/EventsFeed';
import { ReposPanel } from '../components/ReposPanel';
import { InboxForm } from '../components/InboxForm';
import { WaveTelemetryProgress } from '../components/WaveTelemetryProgress';
import { TESTIDS } from '../test/fixtures';
import './Overview.css';

interface OverviewProps {
  agents: Agent[] | null;
  alerts: Alert | null;
  events: string[] | null;
  repos: any[] | null;
}

export function Overview({ agents, alerts, events, repos }: OverviewProps) {
  return (
    <div className="overview" data-testid={TESTIDS.viewOverview}>
      <section className="overview__section overview__section--full">
        <WaveTelemetryProgress />
      </section>

      <section className="overview__section overview__section--full">
        <AgentsPanel agents={agents} />
      </section>

      <section className="overview__section overview__section--row">
        <AlertsPanel alerts={alerts} />
        <EventsFeed events={events} />
        <ReposPanel repos={repos} />
      </section>

      <section className="overview__section overview__section--full">
        <InboxForm />
      </section>
    </div>
  );
}
