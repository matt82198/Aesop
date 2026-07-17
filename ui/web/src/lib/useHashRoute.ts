/**
 * useHashRoute — ~10-line hash-tab routing hook (deliberately NOT react-router; see plan D1).
 * Routes: '#/' (overview), '#/work', '#/activity', '#/cost', '#/prs'.
 * Unknown/empty hashes normalize to '#/'.
 */
import { useEffect, useState } from 'react';

export const ROUTES = ['#/', '#/work', '#/activity', '#/cost', '#/prs'] as const;
export type Route = (typeof ROUTES)[number];

export function normalizeHash(hash: string): Route {
  return (ROUTES as readonly string[]).includes(hash) ? (hash as Route) : '#/';
}

export function useHashRoute(): Route {
  const [route, setRoute] = useState<Route>(() => normalizeHash(window.location.hash));
  useEffect(() => {
    const onHashChange = () => setRoute(normalizeHash(window.location.hash));
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, []);
  return route;
}
