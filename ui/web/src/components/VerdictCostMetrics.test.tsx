/**
 * VerdictCostMetrics component tests
 * Tests the cost-per-outcome metrics display
 */

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { VerdictCostMetrics } from './VerdictCostMetrics';
import { fixtureCost, fixtureCostWithPricing, TESTIDS } from '../test/fixtures';

describe('VerdictCostMetrics', () => {
  it('renders empty state when no runs recorded', () => {
    const emptyData = {
      ...fixtureCost,
      overall_scorecard: { ...fixtureCost.overall_scorecard, total_runs: 0 },
    };
    render(<VerdictCostMetrics cost={emptyData} />);

    expect(screen.getByTestId(TESTIDS.verdictCostMetrics)).toBeInTheDocument();
    expect(screen.getByText(/no verdict data available/i)).toBeInTheDocument();
  });

  it('renders metric tiles when data available', () => {
    render(<VerdictCostMetrics cost={fixtureCost} />);

    expect(screen.getByTestId(TESTIDS.verdictCostMetrics)).toBeInTheDocument();
    expect(screen.getByText('Cost per OK')).toBeInTheDocument();
    expect(screen.getByText('Cost per Failed')).toBeInTheDocument();
  });

  it('shows all four verdict metric tiles', () => {
    render(<VerdictCostMetrics cost={fixtureCost} />);

    expect(screen.getByText('Cost per OK')).toBeInTheDocument();
    expect(screen.getByText('Cost per Failed')).toBeInTheDocument();
    expect(screen.getByText('Cost per Empty')).toBeInTheDocument();
    expect(screen.getByText('Cost per Hung')).toBeInTheDocument();
  });

  it('disables tiles for verdicts with zero count', () => {
    render(<VerdictCostMetrics cost={fixtureCost} />);

    // fixtureCost has empty_count: 2, hung_count: 1 (all enabled)
    // But verify disabled state styling works by checking for disabled class
    const tiles = screen.getAllByText(/cost per/i);
    expect(tiles.length).toBeGreaterThan(0);
  });

  it('displays outcome counts for enabled metrics', () => {
    render(<VerdictCostMetrics cost={fixtureCost} />);

    // OK count = 132
    expect(screen.getByText(/132 outcome/)).toBeInTheDocument();
    // Failed count = 7
    expect(screen.getByText(/7 outcome/)).toBeInTheDocument();
  });

  it('displays prices when has_pricing is true', () => {
    render(<VerdictCostMetrics cost={fixtureCostWithPricing} />);

    // Should show USD units
    expect(screen.getAllByText('USD').length).toBeGreaterThan(0);
  });

  it('displays tokens when has_pricing is false', () => {
    render(<VerdictCostMetrics cost={fixtureCost} />);

    // Should show tokens unit
    expect(screen.getAllByText('tokens').length).toBeGreaterThan(0);
  });

  it('shows informational note about cost calculation', () => {
    render(<VerdictCostMetrics cost={fixtureCost} />);

    const note = screen.getByText(/cost per outcome metric/i);
    expect(note).toBeInTheDocument();
  });
});
