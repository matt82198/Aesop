/**
 * FailureDrilldown tests — collapse/expand, loading, ready, error, and
 * gh-unavailable states. The component takes an injectable `fetcher` so
 * tests never touch the global fetch.
 */

import { describe, it, expect } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { FailureDrilldown } from './FailureDrilldown';
import {
  fixtureWaveFailureData,
  fixtureWaveFailureDataUnavailable,
  fixtureWaveFailureDataEmpty,
  TESTIDS,
} from '../test/fixtures';
import type { WaveFailureData } from '../lib/types';

const ready = (data: WaveFailureData) => () => Promise.resolve(data);

describe('FailureDrilldown', () => {
  it('renders the toggle button', () => {
    render(
      <FailureDrilldown
        prNumber={172}
        fetcher={ready(fixtureWaveFailureData)}
      />
    );
    const toggle = screen.getByTestId(TESTIDS.failureDrilldownToggle);
    expect(toggle).toBeInTheDocument();
    expect(toggle.textContent).toMatch(/drill down/i);
  });

  it('starts in collapsed state', () => {
    render(
      <FailureDrilldown
        prNumber={172}
        fetcher={ready(fixtureWaveFailureData)}
      />
    );
    const content = screen.queryByTestId(TESTIDS.failureDrilldownContent);
    expect(content).not.toBeInTheDocument();
  });

  it('shows loading state while fetching', async () => {
    const user = await userEvent.setup();
    const neverResolving = () => new Promise<WaveFailureData>(() => {});
    render(
      <FailureDrilldown
        prNumber={172}
        fetcher={neverResolving}
      />
    );
    const toggle = screen.getByTestId(TESTIDS.failureDrilldownToggle);
    await user.click(toggle);

    expect(screen.getByTestId(TESTIDS.failureDrilldownLoading)).toBeInTheDocument();
  });

  it('expands and shows run summary when data arrives', async () => {
    const user = await userEvent.setup();
    render(
      <FailureDrilldown
        prNumber={172}
        fetcher={ready(fixtureWaveFailureData)}
      />
    );
    const toggle = screen.getByTestId(TESTIDS.failureDrilldownToggle);
    await user.click(toggle);

    const content = await screen.findByTestId(TESTIDS.failureDrilldownContent);
    expect(content).toBeInTheDocument();

    const run = await screen.findByTestId(TESTIDS.failureDrilldownRun);
    expect(run.textContent).toContain('Failed');
    expect(run.textContent).toContain('CI / test');
  });

  it('renders one job per job in the run', async () => {
    const user = await userEvent.setup();
    render(
      <FailureDrilldown
        prNumber={172}
        fetcher={ready(fixtureWaveFailureData)}
      />
    );
    const toggle = screen.getByTestId(TESTIDS.failureDrilldownToggle);
    await user.click(toggle);

    const jobs = await screen.findAllByTestId(TESTIDS.failureDrilldownJob);
    expect(jobs.length).toBe(fixtureWaveFailureData.jobs.length);
  });

  it('shows job name and status', async () => {
    const user = await userEvent.setup();
    render(
      <FailureDrilldown
        prNumber={172}
        fetcher={ready(fixtureWaveFailureData)}
      />
    );
    const toggle = screen.getByTestId(TESTIDS.failureDrilldownToggle);
    await user.click(toggle);

    await screen.findByTestId(TESTIDS.failureDrilldownContent);
    expect(screen.getByText(/test \(ubuntu\)/)).toBeInTheDocument();
    expect(screen.getByText(/lint \(ubuntu\)/)).toBeInTheDocument();
  });

  it('expands individual jobs to show logs', async () => {
    const user = await userEvent.setup();
    render(
      <FailureDrilldown
        prNumber={172}
        fetcher={ready(fixtureWaveFailureData)}
      />
    );
    const toggle = screen.getByTestId(TESTIDS.failureDrilldownToggle);
    await user.click(toggle);

    const jobs = await screen.findAllByTestId(TESTIDS.failureDrilldownJob);
    // Click the first job (the failing one)
    const firstJobButton = within(jobs[0]).getByRole('button');
    await user.click(firstJobButton);

    // Should show the log excerpt
    const logs = screen.getAllByTestId(TESTIDS.failureDrilldownLogExcerpt);
    expect(logs.length).toBeGreaterThan(0);
    expect(logs[0].textContent).toContain('test suite failed');
  });

  it('shows error state on fetch failure', async () => {
    const user = await userEvent.setup();
    const failingFetch = () => Promise.reject(new Error('Network error'));
    render(
      <FailureDrilldown
        prNumber={172}
        fetcher={failingFetch}
      />
    );
    const toggle = screen.getByTestId(TESTIDS.failureDrilldownToggle);
    await user.click(toggle);

    const error = await screen.findByTestId(TESTIDS.failureDrilldownError);
    expect(error).toBeInTheDocument();
    expect(error.textContent).toContain('Network error');
  });

  it('shows unavailable state when gh is missing', async () => {
    const user = await userEvent.setup();
    render(
      <FailureDrilldown
        prNumber={172}
        fetcher={ready(fixtureWaveFailureDataUnavailable)}
      />
    );
    const toggle = screen.getByTestId(TESTIDS.failureDrilldownToggle);
    await user.click(toggle);

    const unavailable = await screen.findByTestId(TESTIDS.failureDrilldownUnavailable);
    expect(unavailable).toBeInTheDocument();
    expect(unavailable.textContent).toContain('GitHub CLI unavailable');
  });

  it('shows empty state when no runs exist', async () => {
    const user = await userEvent.setup();
    render(
      <FailureDrilldown
        prNumber={173}
        fetcher={ready(fixtureWaveFailureDataEmpty)}
      />
    );
    const toggle = screen.getByTestId(TESTIDS.failureDrilldownToggle);
    await user.click(toggle);

    const empty = await screen.findByTestId(TESTIDS.failureDrilldownEmpty);
    expect(empty).toBeInTheDocument();
    expect(empty.textContent).toMatch(/no workflow runs/i);
  });

  it('collapses when clicked again', async () => {
    const user = await userEvent.setup();
    render(
      <FailureDrilldown
        prNumber={172}
        fetcher={ready(fixtureWaveFailureData)}
      />
    );
    const toggle = screen.getByTestId(TESTIDS.failureDrilldownToggle);

    // Expand
    await user.click(toggle);
    await screen.findByTestId(TESTIDS.failureDrilldownContent);
    expect(screen.getByTestId(TESTIDS.failureDrilldownContent)).toBeInTheDocument();

    // Collapse
    await user.click(toggle);
    expect(screen.queryByTestId(TESTIDS.failureDrilldownContent)).not.toBeInTheDocument();
  });

  it('shows job count summary', async () => {
    const user = await userEvent.setup();
    render(
      <FailureDrilldown
        prNumber={172}
        fetcher={ready(fixtureWaveFailureData)}
      />
    );
    const toggle = screen.getByTestId(TESTIDS.failureDrilldownToggle);
    await user.click(toggle);

    const content = await screen.findByTestId(TESTIDS.failureDrilldownContent);
    // Fixture has 1 failing job
    expect(content.textContent).toMatch(/1.*job.*failed/i);
  });
});
