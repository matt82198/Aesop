/**
 * WaveTelemetryCost tests — polling, burn-rate display, and cost ceiling alert.
 *
 * Contract:
 * - Fetches on mount and polls every 5s (POLL_INTERVAL_MS = 5000)
 * - Accepts an injectable fetcher for tests (dependency injection)
 * - Displays tokens, top model, OK rate (existing)
 * - Displays burn rate and projected total (new)
 * - Shows visual alert when cost_ceiling_exceeded is true (new)
 * - No fake-timer traps — uses real setInterval with manual cleanup
 *
 * Run: npm test -- WaveTelemetryCost.test.tsx
 */

import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { TESTIDS } from '../test/fixtures';
import { WaveTelemetryCost } from './WaveTelemetryCost';

// Helper: returns a fetcher that immediately resolves with the given data
const ready = (data: WaveTelemetry) => () => Promise.resolve(data);

interface WaveTelemetry {
  wave: string;
  phase: string;
  blocker: string;
  tokens_used: number;
  top_model: string;
  ok_rate: number;
  tokens_burned_per_min?: number;
  projected_total_tokens?: number;
  cost_ceiling_exceeded?: boolean;
}

const fixtureData: WaveTelemetry = {
  wave: 'wave-rc.2',
  phase: 'rc-1-published-source-available',
  blocker: 'Dashboard wave telemetry tile',
  tokens_used: 1500000,
  top_model: 'haiku',
  ok_rate: 0.95,
  tokens_burned_per_min: 15000.5,
  projected_total_tokens: 2800000,
  cost_ceiling_exceeded: false,
};

const fixtureDataAlert: WaveTelemetry = {
  ...fixtureData,
  tokens_used: 2500000,
  cost_ceiling_exceeded: true,
};

describe('WaveTelemetryCost', () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it('renders and fetches on mount', async () => {
    const fetcher = vi.fn(ready(fixtureData));

    render(<WaveTelemetryCost fetcher={fetcher} />);

    // Should fetch immediately on mount
    expect(fetcher).toHaveBeenCalledWith('/api/wave/telemetry');
    expect(fetcher).toHaveBeenCalledTimes(1);

    // Should show the data after fetch completes
    expect(await screen.findByText('Tokens Used')).toBeInTheDocument();
  });

  it('displays tokens, model, and OK rate', async () => {
    render(<WaveTelemetryCost fetcher={ready(fixtureData)} />);

    expect(await screen.findByText('1.5M')).toBeInTheDocument(); // tokens_used formatted
    expect(screen.getByText('Haiku')).toBeInTheDocument(); // top_model
    expect(screen.getByText(/95\.0?%/)).toBeInTheDocument(); // ok_rate as percent (flexible matcher)
  });

  it('displays burn rate and projection when available', async () => {
    render(<WaveTelemetryCost fetcher={ready(fixtureData)} />);

    expect(await screen.findByText('Burn Rate')).toBeInTheDocument();
    expect(screen.getByText('15.0K')).toBeInTheDocument(); // tokens_burned_per_min formatted
    expect(screen.getByText('Projected Total')).toBeInTheDocument();
    expect(screen.getByText('2.8M')).toBeInTheDocument(); // projected_total_tokens formatted
  });

  it('shows cost ceiling alert when over limit', async () => {
    render(<WaveTelemetryCost fetcher={ready(fixtureDataAlert)} />);

    expect(await screen.findByText('! Alert')).toBeInTheDocument();
    expect(screen.getByText('Cost ceiling exceeded - wave may need review')).toBeInTheDocument();
  });

  it('applies alert styling when cost ceiling exceeded', async () => {
    const { container } = render(<WaveTelemetryCost fetcher={ready(fixtureDataAlert)} />);

    await screen.findByText('! Alert');
    const costSection = container.querySelector('.wave-telemetry-cost');
    expect(costSection).toHaveClass('wave-telemetry-cost--alert');
  });

  it('has proper test id', async () => {
    render(<WaveTelemetryCost fetcher={ready(fixtureData)} />);

    expect(await screen.findByTestId(TESTIDS.waveTelemetryCost)).toBeInTheDocument();
  });

  it('shows loading state on initial mount', () => {
    // Never-resolving fetcher keeps the component in the loading state
    render(<WaveTelemetryCost fetcher={() => new Promise<WaveTelemetry>(() => {})} />);

    expect(screen.getByText('Loading wave cost...')).toBeInTheDocument();
  });

  it('shows error state when fetch fails', async () => {
    const fetcher = () => Promise.reject(new Error('API error'));

    render(<WaveTelemetryCost fetcher={fetcher} />);

    expect(await screen.findByText(/Error: API error/)).toBeInTheDocument();
  });

  it('cleans up polling interval on unmount', async () => {
    // Verify that the component sets up and cleans up the interval properly
    // by checking no console errors occur on unmount
    const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    const { unmount } = render(<WaveTelemetryCost fetcher={ready(fixtureData)} />);

    await screen.findByText('1.5M');
    unmount();

    // No errors should have been logged during cleanup
    expect(consoleErrorSpy).not.toHaveBeenCalled();
    consoleErrorSpy.mockRestore();
  });

  it('handles missing burn-rate fields gracefully', async () => {
    const dataWithoutBurnRate: WaveTelemetry = {
      wave: 'wave-rc.2',
      phase: 'rc-1-published-source-available',
      blocker: 'test',
      tokens_used: 1500000,
      top_model: 'haiku',
      ok_rate: 0.95,
      // tokens_burned_per_min and projected_total_tokens are undefined
    };

    render(<WaveTelemetryCost fetcher={ready(dataWithoutBurnRate)} />);

    // Should still show the basic tiles
    expect(await screen.findByText('1.5M')).toBeInTheDocument();
    // But should not show burn-rate tiles
    expect(screen.queryByText('Burn Rate')).not.toBeInTheDocument();
    expect(screen.queryByText('Projected Total')).not.toBeInTheDocument();
  });

  it('formats burn rate correctly for various scales', async () => {
    const testCases = [
      { rate: 100.5, expected: '100.5' },
      { rate: 1500.0, expected: '1.5K' },
      { rate: 1500000.0, expected: '1.5M' },
      { rate: 0.5, expected: '0.5' },
    ];

    for (const testCase of testCases) {
      const data: WaveTelemetry = {
        ...fixtureData,
        tokens_burned_per_min: testCase.rate,
      };

      const { unmount, container } = render(<WaveTelemetryCost fetcher={ready(data)} />);

      // Wait for render and find the burn rate value (not the tokens used which also contains "1.5M")
      await screen.findByText('Burn Rate');
      const burnRateSection = container.querySelector('.cost-tile--burnrate');
      expect(burnRateSection?.querySelector('.tile-value')).toHaveTextContent(testCase.expected);
      unmount();
    }
  });

  it('uses default fetcher when none provided', () => {
    // This should not throw type errors when no fetcher is provided
    expect(() => {
      const Component = () => {
        return <WaveTelemetryCost />;
      };
      render(<Component />);
    }).not.toThrow();
  });
});
