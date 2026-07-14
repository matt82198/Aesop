# Contributing to the Aesop dashboard UI — the rules (one page)

These are the baseline rules every component in `ui/web/src/` must follow.
They are enforced by the wave-14 proofs (`tools/verify_dash.py` + vitest); a
violation is a CI failure, not a style nit.

## Interactive elements are real elements

- Anything clickable is a `<button type="button">` (actions) or an `<a href>`
  (navigation). **Never** a `div`/`span` with `onClick`/`tabIndex` — the old
  dashboard's div-with-tabIndex pattern is banned (plan D5).
- Anything focusable must show the focus ring. Do not add `outline: none`
  anywhere; `global.css` already provides `:focus-visible` rings.
- Form controls get a `<label>` (visually hidden with `.sr-only` if needed).

## data-testid contract

- Every testid comes from the `TESTIDS` map in `src/test/fixtures.ts`.
  Add new ids there first; never inline a bare string. U8's Playwright proofs
  assert only via these hooks — renaming one breaks CI.

## Types and fixtures

- All API payload types live in `src/lib/types.ts` — import them, don't
  redeclare shapes. New endpoint? Add the type there in the same PR.
- Component tests render from the fixtures in `src/test/fixtures.ts`.
  Extend the fixtures rather than hand-rolling payload literals per test.

## Styling

- Colors/spacing/type come from the custom properties in
  `src/styles/theme.css` (the design-tokens file — named `theme.css`, not
  `tokens.css`, because the pre-push secret-scan gate blocks any filename
  matching `*token*`). No hex literals in components — both themes must
  work, and tokens are the only way that stays true.
- Honor `prefers-reduced-motion`: the global block handles CSS transitions;
  don't add JS-driven animation without a reduced-motion check.

## Safety

- Any URL that ends up in an `href` goes through `src/lib/sanitizeUrl.ts`.
  When it returns `null`, render the text without an href (inert).
- All mutations go through `src/lib/api.ts` (CSRF header handled there).
  Never call `fetch` with `method: 'POST'` directly from a component.

## Build discipline (D2)

- If you change `ui/web/src/**`, run `npm run build` and commit `ui/web/dist/`
  in the same PR — CI's drift gate rebuilds and compares.
