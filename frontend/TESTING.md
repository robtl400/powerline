# Frontend Testing

## Philosophy

Tests make vibe coding safe. Without them, moving fast is just yolo coding. With them, it's a superpower — you can refactor, extend, and ship with confidence.

## Framework

**Vitest** v4 + **@testing-library/react** + **jsdom**

## Running Tests

```bash
cd frontend
npm test          # run once
npm run test:watch  # watch mode
```

## Test Directory

`src/test/` — all test files live here.

## Test Layers

| Layer | What | Where |
|-------|------|--------|
| Unit | Pure logic functions (column mapping, CSV transforms) | `src/test/*.test.ts` |
| Component | React components in isolation (future) | `src/test/*.test.tsx` |

## Conventions

- Test files: `src/test/<module>.test.ts` or `.test.tsx`
- Import from the source module or replicate the logic under test
- Use `describe` blocks per function, `it` for each case
- Assertions: test actual behavior, not just "it renders" or "it doesn't throw"

## Test Expectations

- 100% test coverage is the goal — tests are what make vibe coding safe
- When writing new pure functions, write corresponding tests
- When fixing a bug, add a regression test
- When adding a conditional (if/else, switch), write tests for BOTH branches
- Never commit code that makes existing tests fail
