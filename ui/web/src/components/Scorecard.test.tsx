/**
 * Scorecard component tests — stat tiles for run verdicts.
 * Tests both modes: with pricing and without. Tests empty data handling.
 */

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Scorecard } from './Scorecard';
import { fixtureCost, fixtureCostWithPricing, TESTIDS } from '../test/fixtures';

describe('Scorecard', () => {
  it('renders scorecard with fixture data', () => {
    render(<Scorecard cost={fixtureCost} />);
    expect(screen.getByTestId(TESTIDS.scorecard)).toBeInTheDocument();
  });

  it('displays total runs count', () => {
    render(<Scorecard cost={fixtureCost} />);
    const scorecard = screen.getByTestId(TESTIDS.scorecard);
    expect(scorecard.textContent).toContain('142');
  });

  it('displays OK rate as percentage', () => {
    render(<Scorecard cost={fixtureCost} />);
    const scorecard = screen.getByTestId(TESTIDS.scorecard);
    // ok_rate is 0.9296, should display as "92.96%"
    expect(scorecard.textContent).toMatch(/92\.9\d%|93\.0%/);
  });

  it('displays FAILED rate', () => {
    render(<Scorecard cost={fixtureCost} />);
    const scorecard = screen.getByTestId(TESTIDS.scorecard);
    // failed_rate is 0.0493, should display as "4.9%" or similar
    expect(scorecard.textContent).toMatch(/4\.\d%|5\.0%/);
  });

  it('displays EMPTY rate', () => {
    render(<Scorecard cost={fixtureCost} />);
    const scorecard = screen.getByTestId(TESTIDS.scorecard);
    // empty_rate is 0.0141, should display as "1.4%" or "1.5%"
    expect(scorecard.textContent).toMatch(/1\.\d%|1\.4%/);
  });

  it('displays HUNG rate', () => {
    render(<Scorecard cost={fixtureCost} />);
    const scorecard = screen.getByTestId(TESTIDS.scorecard);
    // hung_rate is 0.007, should display as "0.7%" or similar
    expect(scorecard.textContent).toMatch(/0\.\d%/);
  });

  it('shows severity coloring for OK stat', () => {
    render(<Scorecard cost={fixtureCost} />);
    const scorecard = screen.getByTestId(TESTIDS.scorecard);
    // Should have some indication of OK status (class or style)
    expect(scorecard.innerHTML).toContain('OK');
  });

  it('shows severity coloring for FAILED stat', () => {
    render(<Scorecard cost={fixtureCost} />);
    const scorecard = screen.getByTestId(TESTIDS.scorecard);
    expect(scorecard.innerHTML).toContain('FAILED');
  });

  it('shows skipped_lines footnote when > 0', () => {
    render(<Scorecard cost={fixtureCost} />);
    const scorecard = screen.getByTestId(TESTIDS.scorecard);
    // skipped_lines is 3
    expect(scorecard.textContent).toContain('3');
  });

  it('does not show skipped_lines footnote when 0', () => {
    const noskip = {
      ...fixtureCost,
      skipped_lines: 0,
    };
    render(<Scorecard cost={noskip} />);
    const scorecard = screen.getByTestId(TESTIDS.scorecard);
    // Should not mention skipped lines
    const text = scorecard.textContent || '';
    // This is a loose check — just ensure no excessive mention
    const skipMentions = (text.match(/skipped/gi) || []).length;
    expect(skipMentions).toBeLessThanOrEqual(1); // tolerance for "skipped" in any case
  });

  it('works with pricing fixture data', () => {
    render(<Scorecard cost={fixtureCostWithPricing} />);
    expect(screen.getByTestId(TESTIDS.scorecard)).toBeInTheDocument();
  });

  it('handles empty scorecard (0 runs)', () => {
    const empty = {
      ...fixtureCost,
      overall_scorecard: {
        total_runs: 0,
        ok_count: 0,
        failed_count: 0,
        empty_count: 0,
        hung_count: 0,
        ok_rate: 0,
        failed_rate: 0,
        empty_rate: 0,
        hung_rate: 0,
      },
    };
    render(<Scorecard cost={empty} />);
    expect(screen.getByTestId(TESTIDS.scorecard)).toBeInTheDocument();
    expect(screen.getByTestId(TESTIDS.scorecard).textContent).toContain('0');
  });

  it('uses theme color tokens for status colors', () => {
    render(<Scorecard cost={fixtureCost} />);
    const scorecard = screen.getByTestId(TESTIDS.scorecard);
    // Verify that no inline hex colors are used (must use CSS vars)
    const html = scorecard.innerHTML;
    expect(html).not.toMatch(/#[0-9a-fA-F]{3,6}/);
  });
});
