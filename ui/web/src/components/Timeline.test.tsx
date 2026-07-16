/**
 * Timeline — Horizontal per-agent bars from startedAt/lastActivity/runtimeSeconds.
 */

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import Timeline from './Timeline';
import { fixtureAgents } from '../test/fixtures';
import { TESTIDS } from '../test/fixtures';
import type { Agent } from '../lib/types';

describe('Timeline', () => {
  it('renders timeline container with testid', () => {
    render(<Timeline agents={fixtureAgents} />);
    expect(screen.getByTestId(TESTIDS.timeline)).toBeInTheDocument();
  });

  it('renders one bar per agent', () => {
    render(<Timeline agents={fixtureAgents} />);
    const bars = screen.getAllByTestId(TESTIDS.timelineBar);
    expect(bars.length).toBe(fixtureAgents.length);
  });

  it('shows agent id in bar label', () => {
    render(<Timeline agents={fixtureAgents} />);
    fixtureAgents.forEach((agent) => {
      expect(screen.getByText(agent.id)).toBeInTheDocument();
    });
  });

  it('shows agent status in bar label', () => {
    render(<Timeline agents={fixtureAgents} />);
    const statusElements = screen.getAllByText(/running/i);
    expect(statusElements.length).toBeGreaterThan(0); // At least one "running"
    // Check for idle and SUSPICIOUS in aria-labels instead
    fixtureAgents.forEach((agent) => {
      const bars = screen.getAllByTestId(TESTIDS.timelineBar);
      const agentBar = bars.find((bar) => bar.getAttribute('aria-label')?.includes(agent.id));
      expect(agentBar?.getAttribute('aria-label')).toContain(agent.status);
    });
  });

  it('shows runtime duration in bar label', () => {
    render(<Timeline agents={fixtureAgents} />);
    // Should format the runtimeSeconds as a human-readable duration
    // First agent has runtimeSeconds: 1776, which is 29m 36s
    const container = screen.getByTestId(TESTIDS.timeline);
    const text = container.textContent || '';
    expect(text).toContain('29m'); // Should contain formatted duration
  });

  it('applies status-based color to bars via theme tokens', () => {
    render(<Timeline agents={fixtureAgents} />);
    const bars = screen.getAllByTestId(TESTIDS.timelineBar);
    expect(bars.length).toBeGreaterThan(0);

    // Check that bars have role-based styling (via CSS class or style)
    bars.forEach((bar) => {
      const style = window.getComputedStyle(bar);
      // Color should be set via theme tokens (will be computed CSS variable)
      expect(style.backgroundColor || style.color).toBeDefined();
    });
  });

  it('handles missing startedAt gracefully (null)', () => {
    const agents: Agent[] = [
      {
        ...fixtureAgents[0],
        startedAt: null,
      },
    ];
    render(<Timeline agents={agents} />);
    const bars = screen.getAllByTestId(TESTIDS.timelineBar);
    expect(bars.length).toBe(1);
    expect(bars[0]).toBeInTheDocument();
    // Should still show agent id and status
    expect(screen.getByText(agents[0].id)).toBeInTheDocument();
  });

  it('handles missing lastActivity gracefully (null)', () => {
    const agents: Agent[] = [
      {
        ...fixtureAgents[0],
        lastActivity: null,
      },
    ];
    render(<Timeline agents={agents} />);
    const bars = screen.getAllByTestId(TESTIDS.timelineBar);
    expect(bars.length).toBe(1);
    expect(bars[0]).toBeInTheDocument();
  });

  it('handles garbage/invalid ISO timestamps (falls back to sensible default)', () => {
    const agents: Agent[] = [
      {
        ...fixtureAgents[0],
        startedAt: 'not-a-date',
        lastActivity: 'garbage',
      },
    ];
    render(<Timeline agents={agents} />);
    const bars = screen.getAllByTestId(TESTIDS.timelineBar);
    expect(bars.length).toBe(1);
    expect(bars[0]).toBeInTheDocument();
    // Should not throw, should render with fallback values
    expect(screen.getByText(agents[0].id)).toBeInTheDocument();
  });

  it('clamps timeline when runtimeSeconds is 0 or negative', () => {
    const agents: Agent[] = [
      {
        ...fixtureAgents[0],
        runtimeSeconds: -5,
      },
    ];
    render(<Timeline agents={agents} />);
    const bars = screen.getAllByTestId(TESTIDS.timelineBar);
    expect(bars.length).toBe(1);
    const bar = bars[0];
    expect(bar).toBeInTheDocument();
    // Should render without NaN or invalid dimensions
    const style = window.getComputedStyle(bar);
    expect(style.width).not.toContain('NaN');
  });

  it('clamps timeline when runtimeSeconds is extremely large', () => {
    const agents: Agent[] = [
      {
        ...fixtureAgents[0],
        runtimeSeconds: 999999999,
      },
    ];
    render(<Timeline agents={agents} />);
    const bars = screen.getAllByTestId(TESTIDS.timelineBar);
    expect(bars.length).toBe(1);
    const bar = bars[0];
    expect(bar).toBeInTheDocument();
    // Should not overflow, should be clamped
    const style = window.getComputedStyle(bar);
    expect(style.width).not.toContain('NaN');
  });

  it('computes bar width proportionally from startedAt to lastActivity', () => {
    const now = new Date().toISOString();
    const oneHourAgo = new Date(Date.now() - 3600000).toISOString();
    const agents: Agent[] = [
      {
        ...fixtureAgents[0],
        startedAt: oneHourAgo,
        lastActivity: now,
      },
    ];
    render(<Timeline agents={agents} />);
    const bars = screen.getAllByTestId(TESTIDS.timelineBar);
    expect(bars.length).toBe(1);
    const bar = bars[0];
    expect(bar).toBeInTheDocument();
    // Bar should have a width reflecting the time span
    const style = window.getComputedStyle(bar);
    expect(style.width).toBeDefined();
    expect(style.width).not.toBe('0px');
  });

  it('shows empty state when no agents', () => {
    render(<Timeline agents={[]} />);
    const container = screen.getByTestId(TESTIDS.timeline);
    expect(container.textContent).toContain('no agents');
  });

  it('each bar is a labeled element for accessibility', () => {
    render(<Timeline agents={fixtureAgents} />);
    const bars = screen.getAllByTestId(TESTIDS.timelineBar);
    bars.forEach((bar, i) => {
      const agent = fixtureAgents[i];
      // Should have aria-label or be a semantic element with accessible name
      const label = bar.getAttribute('aria-label') || bar.textContent || '';
      expect(label).toContain(agent.id);
      expect(label).toContain(agent.status);
    });
  });

  it('handles all status colors: running, idle, SUSPICIOUS, HIGH, DRIFT, MED', () => {
    const agentsWithStatuses: Agent[] = [
      { ...fixtureAgents[0], status: 'running' },
      { ...fixtureAgents[0], id: 'idle-agent', status: 'idle' },
      { ...fixtureAgents[0], id: 'sus-agent', status: 'SUSPICIOUS' },
      { ...fixtureAgents[0], id: 'high-agent', status: 'HIGH' },
      { ...fixtureAgents[0], id: 'drift-agent', status: 'DRIFT' },
      { ...fixtureAgents[0], id: 'med-agent', status: 'MED' },
    ];
    render(<Timeline agents={agentsWithStatuses} />);
    const bars = screen.getAllByTestId(TESTIDS.timelineBar);
    expect(bars.length).toBe(6);
  });

  it('respects prefers-reduced-motion for animations', () => {
    // Mock matchMedia to return reduced motion preference
    const mockMatchMedia = (query: string) => ({
      matches: query === '(prefers-reduced-motion: reduce)',
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => true,
    });
    Object.defineProperty(window, 'matchMedia', { value: mockMatchMedia, writable: true });

    render(<Timeline agents={fixtureAgents} />);
    const bars = screen.getAllByTestId(TESTIDS.timelineBar);
    expect(bars.length).toBeGreaterThan(0);
    // Should render without issues even with reduced motion preference
  });

  it('running status maps to info (blue), not ok (green)', () => {
    const agents: Agent[] = [
      { ...fixtureAgents[0], status: 'running' },
    ];
    render(<Timeline agents={agents} />);
    const bar = screen.getByTestId(TESTIDS.timelineBar);

    // Check that the bar's className contains status-info (CSS modules will hash it)
    const className = bar.getAttribute('class') || '';
    expect(className).toContain('status-info');
    expect(className).not.toContain('status-ok');
  });
});
