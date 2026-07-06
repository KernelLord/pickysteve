---
id: tdd-workflow
name: TDD Workflow
description: Test-driven development — write the failing test first, then the minimal code, then refactor.
tags: [tdd, testing, test-first, red-green-refactor, unit-tests, coverage, design]
---
# TDD Workflow

Use when building a new feature or fixing a bug and you want tests to drive the
design rather than be bolted on after.

## Capabilities
- Red-green-refactor loop with forcing questions about behavior before code.
- Turning a vague requirement into concrete, falsifiable test cases (incl. edge cases).
- Test granularity: unit vs integration boundaries, what to mock and what not to.
- Bug-fix discipline: reproduce with a failing test first, then fix.
- Keeps tests behavior-focused so they survive refactors.

## Notes
Methodology, language-agnostic. Pairs with the language reviewers for idiom.
