import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ReposPanel } from './ReposPanel';
import { fixtureRepos, TESTIDS } from '../test/fixtures';

describe('ReposPanel', () => {
  it('renders repos list', () => {
    render(<ReposPanel repos={fixtureRepos} />);

    expect(screen.getByTestId(TESTIDS.reposPanel)).toBeInTheDocument();
    expect(screen.getByText('aesop')).toBeInTheDocument();
    expect(screen.getByText('tr-sample-tracker')).toBeInTheDocument();
  });

  it('renders repo status', () => {
    render(<ReposPanel repos={fixtureRepos} />);

    // Multiple repos have "clean" status, so use getAllByText
    const cleanElements = screen.getAllByText('clean');
    expect(cleanElements.length).toBeGreaterThan(0);
    expect(screen.getByText(/dirty/)).toBeInTheDocument();
  });

  it('renders empty state when no repos', () => {
    render(<ReposPanel repos={[]} />);

    expect(screen.getByText('No repositories.')).toBeInTheDocument();
  });

  it('renders empty state when repos is null', () => {
    render(<ReposPanel repos={null} />);

    expect(screen.getByText('No repositories.')).toBeInTheDocument();
  });

  it('applies severity-based styling based on repo state', () => {
    render(<ReposPanel repos={fixtureRepos} />);

    const items = screen.getAllByRole('listitem');
    // First repo is clean
    expect(items[0]).toHaveAttribute('data-severity', 'ok');
    // Second repo is dirty
    expect(items[1]).toHaveAttribute('data-severity', 'warn');
  });
});
