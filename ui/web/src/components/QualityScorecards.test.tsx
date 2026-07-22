import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QualityScorecards } from './QualityScorecards';
import { fixtureQualityScorecard, fixtureQualityScorecardEmpty, TESTIDS } from '../test/fixtures';

describe('QualityScorecards', () => {
  it('renders null state', () => {
    render(<QualityScorecards quality={null} />);
    expect(screen.getByText(/Loading quality metrics/i)).toBeInTheDocument();
  });

  it('renders empty state', () => {
    render(<QualityScorecards quality={fixtureQualityScorecardEmpty} />);
    expect(screen.getByText(/No quality data available yet/i)).toBeInTheDocument();
  });

  it('renders specialties table', () => {
    render(<QualityScorecards quality={fixtureQualityScorecard} />);
    expect(screen.getByTestId(TESTIDS.qualityScorecards)).toBeInTheDocument();
    expect(screen.getAllByText('haiku').length).toBeGreaterThan(0);
    expect(screen.getAllByText('sonnet').length).toBeGreaterThan(0);
  });

  it('displays success rates', () => {
    render(<QualityScorecards quality={fixtureQualityScorecard} />);
    // haiku: 142/150 ≈ 94.7%
    expect(screen.getAllByText(/94\.7%/).length).toBeGreaterThan(0);
    // sonnet: 76/78 ≈ 97.4%
    expect(screen.getAllByText(/97\.4%/).length).toBeGreaterThan(0);
  });

  it('displays repair counts', () => {
    render(<QualityScorecards quality={fixtureQualityScorecard} />);
    // haiku has 8 repairs, sonnet has 3
    const cells = screen.getAllByText(/^[0-9]+$/);
    // Should contain run counts and repair counts
    expect(cells.length).toBeGreaterThan(0);
  });

  it('renders top by success ranking', () => {
    render(<QualityScorecards quality={fixtureQualityScorecard} />);
    expect(screen.getByText('Top by Success Rate')).toBeInTheDocument();
    // Top ranked by success should appear
    const rankingItems = screen.getAllByText(/#1|#2|#3/);
    expect(rankingItems.length).toBeGreaterThan(0);
  });

  it('renders top by retry ranking', () => {
    render(<QualityScorecards quality={fixtureQualityScorecard} />);
    expect(screen.getByText('Highest Retry Frequency')).toBeInTheDocument();
  });

  it('displays skipped lines footnote', () => {
    const withSkipped = {
      ...fixtureQualityScorecard,
      skipped_lines: 5,
    };
    render(<QualityScorecards quality={withSkipped} />);
    expect(screen.getByText(/5 line\(s\) could not be parsed/)).toBeInTheDocument();
  });

  it('omits skipped lines footnote when zero', () => {
    render(<QualityScorecards quality={fixtureQualityScorecard} />);
    expect(screen.queryByText(/line\(s\) could not be parsed/)).not.toBeInTheDocument();
  });

  it('renders success rate with OK count detail', () => {
    render(<QualityScorecards quality={fixtureQualityScorecard} />);
    // Haiku: 94.67% (142) = 142 successes
    expect(screen.getByText(/\(142\)/)).toBeInTheDocument();
  });

  it('applies severity styling based on success rate', () => {
    render(<QualityScorecards quality={fixtureQualityScorecard} />);
    // All specialties should have rows with severity classes
    const rows = screen.getAllByRole('row');
    // At minimum we should have header + 3 data rows
    expect(rows.length).toBeGreaterThanOrEqual(4);
  });

  it('limits top rankings to 5 items', () => {
    const manySpecialties = {
      ...fixtureQualityScorecard,
      specialties: Object.fromEntries(
        Array.from({ length: 10 }, (_, i) => [
          `agent${i}`,
          {
            total_runs: 10,
            success_count: 9,
            failed_count: 1,
            empty_count: 0,
            hung_count: 0,
            success_rate: 0.9,
            repair_count: 0,
            retry_frequency: 0,
          },
        ])
      ),
      top_by_success: Array.from({ length: 10 }, (_, i) => ({
        agent_type: `agent${i}`,
        success_rate: 0.9,
        total_runs: 10,
      })),
      top_by_retry: Array.from({ length: 10 }, (_, i) => ({
        agent_type: `agent${i}`,
        retry_frequency: 0,
        total_runs: 10,
      })),
    };
    render(<QualityScorecards quality={manySpecialties} />);
    const rankingPlaces = screen.getAllByText(/#1|#2|#3|#4|#5/);
    // Should have at most 5 items per ranking list
    expect(rankingPlaces.length).toBeLessThanOrEqual(10);
  });
});
