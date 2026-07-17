/**
 * AgentInspector tests — the read-only drawer's contract: dialog semantics,
 * loading / ready / error / empty states, status-as-text (not color alone),
 * transcript-tail rendering, XSS-safety (no raw HTML injection), Escape + close
 * button dismissal, and focus behaviour (focus enters the dialog on open,
 * returns to the trigger on close). The component takes an injectable `fetcher`
 * so tests never touch the global fetch.
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import { userEvent } from '@testing-library/user-event';
import { AgentInspector } from './AgentInspector';
import { fixtureAgents, fixtureAgentInspector, TESTIDS } from '../test/fixtures';
import type { AgentInspectorDetail } from '../lib/types';

const agent = fixtureAgents[0];
const ready = (data: AgentInspectorDetail) => () => Promise.resolve(data);

describe('AgentInspector', () => {
  it('renders as a labelled modal dialog', async () => {
    render(<AgentInspector agent={agent} onClose={() => {}} fetcher={ready(fixtureAgentInspector)} />);
    const dialog = await screen.findByTestId(TESTIDS.agentInspector);
    expect(dialog).toHaveAttribute('role', 'dialog');
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(dialog).toHaveAttribute('aria-labelledby');
  });

  it('shows a loading state before detail arrives', () => {
    render(
      <AgentInspector
        agent={agent}
        onClose={() => {}}
        fetcher={() => new Promise<AgentInspectorDetail>(() => {})}
      />
    );
    expect(screen.getByTestId(TESTIDS.agentInspectorLoading)).toBeInTheDocument();
  });

  it('shows status as TEXT, not color alone', async () => {
    render(<AgentInspector agent={agent} onClose={() => {}} fetcher={ready(fixtureAgentInspector)} />);
    const status = await screen.findByTestId(TESTIDS.agentInspectorStatus);
    expect(status.textContent).toContain(agent.status); // 'running'
    // The icon is decorative (aria-hidden) so status never rides on it alone.
    expect(status.querySelector('[aria-hidden="true"]')).not.toBeNull();
  });

  it('renders runtime, tokens, task label, and dispatch prompt', async () => {
    render(<AgentInspector agent={agent} onClose={() => {}} fetcher={ready(fixtureAgentInspector)} />);
    await screen.findByTestId(TESTIDS.agentInspector);
    expect(screen.getByText(agent.taskLabel)).toBeInTheDocument();
    expect(screen.getByText('48,213')).toBeInTheDocument(); // tokensUsed formatted
    expect(await screen.findByText(fixtureAgentInspector.dispatch_prompt)).toBeInTheDocument();
  });

  it('renders one entry per transcript tail line', async () => {
    render(<AgentInspector agent={agent} onClose={() => {}} fetcher={ready(fixtureAgentInspector)} />);
    const entries = await screen.findAllByTestId(TESTIDS.agentInspectorTail);
    expect(entries.length).toBe(fixtureAgentInspector.transcript_tail.length);
    const transcript = screen.getByTestId(TESTIDS.agentInspectorTranscript);
    expect(within(transcript).getByText(/scaffolding AgentsPanel/i)).toBeInTheDocument();
  });

  it('renders transcript text as escaped text — no raw HTML injection', async () => {
    const xss = '<img src=x onerror="window.__xss=1"><script>window.__xss=1</script>';
    const hostile: AgentInspectorDetail = {
      ...fixtureAgentInspector,
      transcript_tail: [{ type: 'user', text: xss }],
    };
    const { container } = render(
      <AgentInspector agent={agent} onClose={() => {}} fetcher={ready(hostile)} />
    );
    await screen.findByTestId(TESTIDS.agentInspectorTranscript);
    // The payload appears verbatim as text…
    expect(screen.getByText(xss)).toBeInTheDocument();
    // …and NO real element was injected into the DOM.
    expect(container.querySelector('img')).toBeNull();
    expect(container.querySelector('script')).toBeNull();
    expect((window as unknown as { __xss?: number }).__xss).toBeUndefined();
  });

  it('renders an empty state when the transcript tail is empty', async () => {
    render(
      <AgentInspector
        agent={agent}
        onClose={() => {}}
        fetcher={ready({ ...fixtureAgentInspector, transcript_tail: [] })}
      />
    );
    expect(await screen.findByTestId(TESTIDS.agentInspectorEmpty)).toBeInTheDocument();
  });

  it('renders an error state when the fetch rejects', async () => {
    render(
      <AgentInspector
        agent={agent}
        onClose={() => {}}
        fetcher={() => Promise.reject(new Error('boom'))}
      />
    );
    const err = await screen.findByTestId(TESTIDS.agentInspectorError);
    expect(err).toHaveAttribute('role', 'alert');
    expect(err.textContent).toContain('boom');
  });

  it('closes on the close button', async () => {
    const onClose = vi.fn();
    render(<AgentInspector agent={agent} onClose={onClose} fetcher={ready(fixtureAgentInspector)} />);
    const close = await screen.findByTestId(TESTIDS.agentInspectorClose);
    await userEvent.click(close);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('closes on Escape', async () => {
    const onClose = vi.fn();
    render(<AgentInspector agent={agent} onClose={onClose} fetcher={ready(fixtureAgentInspector)} />);
    await screen.findByTestId(TESTIDS.agentInspector);
    await userEvent.keyboard('{Escape}');
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('moves focus into the dialog on open and restores it on close', async () => {
    const trigger = document.createElement('button');
    trigger.textContent = 'open';
    document.body.appendChild(trigger);
    trigger.focus();
    expect(document.activeElement).toBe(trigger);

    const { unmount } = render(
      <AgentInspector agent={agent} onClose={() => {}} fetcher={ready(fixtureAgentInspector)} />
    );
    const close = await screen.findByTestId(TESTIDS.agentInspectorClose);
    await waitFor(() => expect(document.activeElement).toBe(close));

    unmount();
    expect(document.activeElement).toBe(trigger);
    trigger.remove();
  });
});
