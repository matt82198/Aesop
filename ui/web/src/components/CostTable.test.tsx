/**
 * CostTable component tests — per-model cost and token display.
 * Tests tokens-only mode (no pricing) and pricing mode separately.
 * Tests proper table semantics, caption, thead/tbody, scope attributes.
 */

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { CostTable } from './CostTable';
import { fixtureCost, fixtureCostWithPricing, TESTIDS } from '../test/fixtures';

describe('CostTable', () => {
  it('renders table with testid', () => {
    render(<CostTable cost={fixtureCost} />);
    expect(screen.getByTestId(TESTIDS.costTable)).toBeInTheDocument();
  });

  it('renders as a proper <table> element', () => {
    render(<CostTable cost={fixtureCost} />);
    const table = screen.getByTestId(TESTIDS.costTable);
    expect(table.tagName).toBe('TABLE');
  });

  it('has a caption describing the table', () => {
    render(<CostTable cost={fixtureCost} />);
    const table = screen.getByTestId(TESTIDS.costTable);
    const caption = table.querySelector('caption');
    expect(caption).toBeInTheDocument();
    expect(caption?.textContent).toBeTruthy();
  });

  it('has proper thead and tbody structure', () => {
    render(<CostTable cost={fixtureCost} />);
    const table = screen.getByTestId(TESTIDS.costTable);
    expect(table.querySelector('thead')).toBeInTheDocument();
    expect(table.querySelector('tbody')).toBeInTheDocument();
  });

  it('has column headers with scope="col"', () => {
    render(<CostTable cost={fixtureCost} />);
    const table = screen.getByTestId(TESTIDS.costTable);
    const ths = table.querySelectorAll('th[scope="col"]');
    expect(ths.length).toBeGreaterThan(0);
  });

  it('lists all models in fixture data', () => {
    render(<CostTable cost={fixtureCost} />);
    expect(screen.getByText(/haiku/i)).toBeInTheDocument();
    expect(screen.getByText(/sonnet/i)).toBeInTheDocument();
  });

  it('displays runs count for each model', () => {
    render(<CostTable cost={fixtureCost} />);
    // haiku has 128 runs
    expect(screen.getByText('128')).toBeInTheDocument();
    // sonnet has 14 runs
    expect(screen.getByText('14')).toBeInTheDocument();
  });

  it('displays token counts in readable format (e.g., "2.1M")', () => {
    render(<CostTable cost={fixtureCost} />);
    const table = screen.getByTestId(TESTIDS.costTable);
    // haiku tokens_in is 2140050, should display as "2.1M"
    expect(table.textContent).toContain('2.1M');
  });

  it('displays verdict counts (OK/FAILED/EMPTY/HUNG)', () => {
    render(<CostTable cost={fixtureCost} />);
    const table = screen.getByTestId(TESTIDS.costTable);
    // haiku has verdicts: OK: 119, FAILED: 6, EMPTY: 2, HUNG: 1
    expect(table.textContent).toContain('119');
    expect(table.textContent).toContain('6');
    expect(table.textContent).toContain('2');
    expect(table.textContent).toContain('1');
  });

  describe('tokens-only mode (no pricing)', () => {
    it('shows tokens columns but no currency columns when has_pricing=false', () => {
      render(<CostTable cost={fixtureCost} />);
      const table = screen.getByTestId(TESTIDS.costTable);
      // Should have "tokens in/out" headers (case-insensitive)
      expect(table.textContent).toMatch(/tokens\s+in/i);
      expect(table.textContent).toMatch(/tokens\s+out/i);
      // Should NOT have a $ symbol (currency) or "estimate" label
      expect(table.innerHTML).not.toContain('$');
    });
  });

  describe('pricing mode', () => {
    it('shows currency columns labeled "estimate" when has_pricing=true', () => {
      render(<CostTable cost={fixtureCostWithPricing} />);
      const table = screen.getByTestId(TESTIDS.costTable);
      // Should show "estimate" label for pricing
      expect(table.textContent).toContain('estimate');
      // Should show $ symbols
      expect(table.innerHTML).toContain('$');
    });

    it('displays dollar amounts for input cost', () => {
      render(<CostTable cost={fixtureCostWithPricing} />);
      const table = screen.getByTestId(TESTIDS.costTable);
      // haiku input_cost is 2.14
      expect(table.textContent).toContain('2.14');
    });

    it('displays dollar amounts for output cost', () => {
      render(<CostTable cost={fixtureCostWithPricing} />);
      const table = screen.getByTestId(TESTIDS.costTable);
      // haiku output_cost is 2.05
      expect(table.textContent).toContain('2.05');
    });

    it('displays total cost', () => {
      render(<CostTable cost={fixtureCostWithPricing} />);
      const table = screen.getByTestId(TESTIDS.costTable);
      // haiku total_cost is 4.19
      expect(table.textContent).toContain('4.19');
    });
  });

  it('handles single row (1 model) without breaking layout', () => {
    const single = {
      ...fixtureCost,
      models: {
        'claude-haiku-4-5-20251001': fixtureCost.models['claude-haiku-4-5-20251001'],
      },
    };
    render(<CostTable cost={single} />);
    const table = screen.getByTestId(TESTIDS.costTable);
    const rows = table.querySelectorAll('tbody tr');
    expect(rows.length).toBe(1);
  });

  it('handles many rows without breaking layout', () => {
    const many = {
      ...fixtureCost,
      models: {
        ...fixtureCost.models,
        'model-1': {
          runs: 10,
          tokens_in: 1000,
          tokens_out: 500,
          verdicts: { OK: 9, FAILED: 1, EMPTY: 0, HUNG: 0 },
        },
        'model-2': {
          runs: 20,
          tokens_in: 2000,
          tokens_out: 1000,
          verdicts: { OK: 18, FAILED: 2, EMPTY: 0, HUNG: 0 },
        },
      },
    };
    render(<CostTable cost={many} />);
    const table = screen.getByTestId(TESTIDS.costTable);
    const rows = table.querySelectorAll('tbody tr');
    expect(rows.length).toBeGreaterThan(2);
  });

  it('uses theme color tokens (no hex colors in output)', () => {
    render(<CostTable cost={fixtureCost} />);
    const table = screen.getByTestId(TESTIDS.costTable);
    // Should not have inline hex color styles
    expect(table.innerHTML).not.toMatch(/#[0-9a-fA-F]{3,6}(?![0-9a-fA-F])/);
  });
});
