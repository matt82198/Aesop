import { describe, it, expect, afterEach } from 'vitest';
import { render, screen, act, fireEvent } from '@testing-library/react';
import App from './App';
import { TESTIDS } from './test/fixtures';

function setHash(hash: string) {
  window.location.hash = hash;
  window.dispatchEvent(new HashChangeEvent('hashchange'));
}

afterEach(() => {
  window.location.hash = '';
  document.documentElement.removeAttribute('data-theme');
  localStorage.clear();
});

describe('App shell', () => {
  it('renders the health header and nav', () => {
    render(<App />);
    expect(screen.getByTestId(TESTIDS.healthHeader)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Overview' })).toHaveAttribute('href', '#/');
    expect(screen.getByRole('link', { name: 'Work' })).toHaveAttribute('href', '#/work');
    expect(screen.getByRole('link', { name: 'Activity' })).toHaveAttribute('href', '#/activity');
    expect(screen.getByRole('link', { name: 'Cost' })).toHaveAttribute('href', '#/cost');
    expect(screen.getByRole('link', { name: 'PR Board' })).toHaveAttribute('href', '#/prs');
  });

  it('renders the overview placeholder by default', () => {
    render(<App />);
    expect(screen.getByTestId(TESTIDS.viewOverview)).toBeInTheDocument();
  });

  it('switches views on hash change', () => {
    render(<App />);
    act(() => setHash('#/work'));
    expect(screen.getByTestId(TESTIDS.viewWork)).toBeInTheDocument();
    expect(screen.queryByTestId(TESTIDS.viewOverview)).not.toBeInTheDocument();

    act(() => setHash('#/cost'));
    expect(screen.getByTestId(TESTIDS.viewCost)).toBeInTheDocument();

    act(() => setHash('#/activity'));
    expect(screen.getByTestId(TESTIDS.viewActivity)).toBeInTheDocument();
  });

  it('marks the active tab with aria-current', () => {
    render(<App />);
    act(() => setHash('#/work'));
    expect(screen.getByRole('link', { name: 'Work' })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('link', { name: 'Overview' })).not.toHaveAttribute('aria-current');
  });

  it('exposes the SSE connection status as a live region', () => {
    render(<App />);
    const status = screen.getByTestId(TESTIDS.sseStatus);
    expect(status).toHaveAttribute('role', 'status');
    expect(status).toHaveAttribute('aria-live', 'polite');
  });

  it('theme toggle is a real button and persists to localStorage', () => {
    render(<App />);
    const toggle = screen.getByTestId(TESTIDS.themeToggle);
    expect(toggle.tagName).toBe('BUTTON');

    fireEvent.click(toggle);
    const stored = localStorage.getItem('aesop-theme');
    expect(stored === 'light' || stored === 'dark').toBe(true);
    expect(document.documentElement.getAttribute('data-theme')).toBe(stored);

    // Toggling again flips the theme
    fireEvent.click(toggle);
    const flipped = localStorage.getItem('aesop-theme');
    expect(flipped).not.toBe(stored);
  });
});
