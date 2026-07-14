/**
 * App shell — sticky HealthHeader slot + hash-tab nav + view slots (D4).
 *
 * U1 renders placeholder views; U4–U7 replace the placeholders with real
 * components. The header slot, nav, theme toggle, and SSE plumbing are the
 * stable shell contract.
 *
 * A11y baseline (D5): all interactive elements are real <button>/<a>,
 * nav uses aria-current="page", the SSE status is a role="status" live region.
 */
import { useCallback, useEffect, useState } from 'react';
import { useHashRoute, type Route } from './lib/useHashRoute';
import { useSSE } from './lib/useSSE';
import { TESTIDS } from './test/fixtures';

const THEME_STORAGE_KEY = 'aesop-theme';
type Theme = 'light' | 'dark' | null; // null = follow OS preference

function readStoredTheme(): Theme {
  try {
    const v = localStorage.getItem(THEME_STORAGE_KEY);
    return v === 'light' || v === 'dark' ? v : null;
  } catch {
    return null;
  }
}

function applyTheme(theme: Theme) {
  const root = document.documentElement;
  if (theme === null) {
    root.removeAttribute('data-theme');
  } else {
    root.setAttribute('data-theme', theme);
  }
}

function useTheme() {
  const [theme, setTheme] = useState<Theme>(readStoredTheme);

  useEffect(() => {
    applyTheme(theme);
    try {
      if (theme === null) {
        localStorage.removeItem(THEME_STORAGE_KEY);
      } else {
        localStorage.setItem(THEME_STORAGE_KEY, theme);
      }
    } catch {
      // localStorage unavailable (private mode) — theme still applies for this session
    }
  }, [theme]);

  const toggle = useCallback(() => {
    setTheme((prev) => {
      const osPrefersDark =
        typeof matchMedia !== 'undefined' &&
        matchMedia('(prefers-color-scheme: dark)').matches;
      const effective = prev ?? (osPrefersDark ? 'dark' : 'light');
      return effective === 'dark' ? 'light' : 'dark';
    });
  }, []);

  return { theme, toggle };
}

const NAV_ITEMS: Array<{ hash: Route; label: string }> = [
  { hash: '#/', label: 'Overview' },
  { hash: '#/work', label: 'Work' },
  { hash: '#/activity', label: 'Activity' },
  { hash: '#/cost', label: 'Cost' },
];

function Placeholder({ name, testid }: { name: string; testid: string }) {
  return (
    <section className="view-placeholder" data-testid={testid} aria-label={`${name} view`}>
      <h2>{name}</h2>
      <p>{name} view lands in a later unit of wave 14.</p>
    </section>
  );
}

export default function App() {
  const route = useHashRoute();
  const sse = useSSE();
  const { theme, toggle } = useTheme();

  const connection = sse.connectionStatus;

  return (
    <>
      <header className="app-header" data-testid={TESTIDS.healthHeader}>
        <span className="app-title">Aesop Fleet</span>
        <nav className="app-nav" aria-label="Views">
          {NAV_ITEMS.map(({ hash, label }) => (
            <a key={hash} href={hash} aria-current={route === hash ? 'page' : undefined}>
              {label}
            </a>
          ))}
        </nav>
        <button
          type="button"
          className="theme-toggle"
          data-testid={TESTIDS.themeToggle}
          onClick={toggle}
          aria-label="Toggle color theme"
        >
          {theme === 'dark' ? 'Light theme' : theme === 'light' ? 'Dark theme' : 'Theme'}
        </button>
        <span
          className="sse-status"
          data-testid={TESTIDS.sseStatus}
          data-status={connection.status}
          role="status"
          aria-live="polite"
        >
          {connection.status === 'live'
            ? 'Live'
            : connection.status === 'reconnecting'
              ? 'Reconnecting…'
              : 'Connection error'}
        </span>
      </header>
      <main className="app-main">
        {route === '#/' && <Placeholder name="Overview" testid={TESTIDS.viewOverview} />}
        {route === '#/work' && <Placeholder name="Work" testid={TESTIDS.viewWork} />}
        {route === '#/activity' && <Placeholder name="Activity" testid={TESTIDS.viewActivity} />}
        {route === '#/cost' && <Placeholder name="Cost" testid={TESTIDS.viewCost} />}
      </main>
    </>
  );
}
