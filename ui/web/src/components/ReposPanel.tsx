/**
 * ReposPanel — Repository status display.
 */

import type { RepoStatus } from '../lib/types';
import { TESTIDS } from '../test/fixtures';
import './ReposPanel.css';

interface ReposPanelProps {
  repos: RepoStatus[] | null;
}

/**
 * Determine repo state severity for color coding.
 */
function getRepoSeverity(state: unknown): 'ok' | 'warn' | 'error' {
  if (typeof state === 'string') {
    if (state.toLowerCase().includes('clean')) return 'ok';
    if (state.toLowerCase().includes('dirty')) return 'warn';
    return 'error';
  }
  return 'ok';
}

export function ReposPanel({ repos }: ReposPanelProps) {
  const hasRepos = repos && repos.length > 0;

  return (
    <section className="repos-panel" data-testid={TESTIDS.reposPanel}>
      <h2>Repositories</h2>
      {!hasRepos ? (
        <p className="empty-state">No repositories.</p>
      ) : (
        <ul className="repos-panel__list">
          {repos.map((repo, idx) => {
            const repoName = repo.repo || `Repo ${idx + 1}`;
            const repoState = repo.state ? String(repo.state) : 'unknown';
            const severity = getRepoSeverity(repoState);

            return (
              <li
                key={idx}
                className="repos-panel__item"
                data-severity={severity}
              >
                <span className="repos-panel__name">{repoName}</span>
                <span
                  className="repos-panel__state"
                  style={{
                    color:
                      severity === 'ok'
                        ? 'var(--color-status-ok)'
                        : severity === 'warn'
                          ? 'var(--color-status-warn)'
                          : 'var(--color-status-error)',
                  }}
                >
                  {repoState}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
