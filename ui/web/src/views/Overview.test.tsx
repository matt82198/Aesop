import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Overview } from './Overview';
import {
  fixtureAgents,
  fixtureAlerts,
  fixtureEvents,
  fixtureRepos,
  TESTIDS,
} from '../test/fixtures';

vi.mock('../components/AgentsPanel', () => ({
  AgentsPanel: () => <div data-testid="agents-panel-mock">AgentsPanel</div>,
}));

vi.mock('../components/AlertsPanel', () => ({
  AlertsPanel: () => <div data-testid="alerts-panel-mock">AlertsPanel</div>,
}));

vi.mock('../components/EventsFeed', () => ({
  EventsFeed: () => <div data-testid="events-feed-mock">EventsFeed</div>,
}));

vi.mock('../components/ReposPanel', () => ({
  ReposPanel: () => <div data-testid="repos-panel-mock">ReposPanel</div>,
}));

vi.mock('../components/InboxForm', () => ({
  InboxForm: () => <div data-testid="inbox-form-mock">InboxForm</div>,
}));

describe('Overview', () => {
  it('renders overview view with all components', () => {
    render(
      <Overview
        agents={fixtureAgents}
        alerts={fixtureAlerts}
        events={fixtureEvents}
        repos={fixtureRepos}
      />
    );

    expect(screen.getByTestId(TESTIDS.viewOverview)).toBeInTheDocument();
    expect(screen.getByTestId('agents-panel-mock')).toBeInTheDocument();
    expect(screen.getByTestId('alerts-panel-mock')).toBeInTheDocument();
    expect(screen.getByTestId('events-feed-mock')).toBeInTheDocument();
    expect(screen.getByTestId('repos-panel-mock')).toBeInTheDocument();
    expect(screen.getByTestId('inbox-form-mock')).toBeInTheDocument();
  });

  it('handles null values gracefully', () => {
    render(
      <Overview
        agents={null}
        alerts={null}
        events={null}
        repos={null}
      />
    );

    expect(screen.getByTestId(TESTIDS.viewOverview)).toBeInTheDocument();
  });

  it('renders with empty arrays', () => {
    render(
      <Overview
        agents={[]}
        alerts={{ count: 0, lines: [] }}
        events={[]}
        repos={[]}
      />
    );

    expect(screen.getByTestId(TESTIDS.viewOverview)).toBeInTheDocument();
  });
});
