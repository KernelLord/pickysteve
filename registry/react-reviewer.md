---
id: react-reviewer
name: React Reviewer
description: Review React/JSX for hook correctness, render performance, server/client component boundaries, and accessibility.
tags: [react, jsx, hooks, frontend, performance, rerender, server-components, a11y]
---
# React Reviewer

Use for any change touching `.tsx`/`.jsx` or React component logic.

## Capabilities
- Hook correctness: exhaustive `useEffect` deps, stale closures, conditional hooks,
  cleanup functions, `useMemo`/`useCallback` that actually pay for themselves.
- Render performance: unnecessary re-renders, unstable props/keys, context that
  re-renders the whole tree, list virtualization.
- Server/client boundaries (RSC/Next.js): `"use client"` placement, passing
  non-serializable props across the boundary, hydration mismatches.
- React-specific security: `dangerouslySetInnerHTML`, untrusted `href`/`src`.
- Accessibility basics: semantic elements, labels, focus management in modals.

## Notes
Framework-aware but library-agnostic across state managers. Flags with concrete fixes.
