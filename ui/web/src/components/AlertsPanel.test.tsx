import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { AlertsPanel } from './AlertsPanel';
import { fixtureAlerts, fixtureAlertsEmpty, TESTIDS } from '../test/fixtures';

describe('AlertsPanel', () => {
  it('renders alerts with severity styling', () => {
    render(<AlertsPanel alerts={fixtureAlerts} />);

    expect(screen.getByTestId(TESTIDS.alertsPanel)).toBeInTheDocument();
    const alertLines = screen.getAllByTestId(TESTIDS.alertLine);
    expect(alertLines).toHaveLength(fixtureAlerts.lines.length);
  });

  it('displays alert severity as text', () => {
    render(<AlertsPanel alerts={fixtureAlerts} />);

    // First line has HIGH
    expect(screen.getByText(/HIGH/)).toBeInTheDocument();
  });

  it('renders empty state when no alerts', () => {
    render(<AlertsPanel alerts={fixtureAlertsEmpty} />);

    expect(screen.getByText('No alerts.')).toBeInTheDocument();
  });

  it('renders empty state when alerts is null', () => {
    render(<AlertsPanel alerts={null} />);

    expect(screen.getByText('No alerts.')).toBeInTheDocument();
  });

  it('applies severity-based styling to alert items', () => {
    render(<AlertsPanel alerts={fixtureAlerts} />);

    const alertItems = screen.getAllByTestId(TESTIDS.alertLine);
    // First alert has HIGH severity
    expect(alertItems[0]).toHaveAttribute('data-severity', 'error');
    // Second alert has MED severity
    expect(alertItems[1]).toHaveAttribute('data-severity', 'warn');
  });

  it('displays alert text content', () => {
    render(<AlertsPanel alerts={fixtureAlerts} />);

    fixtureAlerts.lines.forEach((line) => {
      expect(screen.getByText(line)).toBeInTheDocument();
    });
  });
});
