---
description: React and TypeScript conventions for the panel frontend
paths:
  - "frontend/**"
---

- **Types come from the backend.** `src/shared/api/schema.gen.ts` is generated
  by `npm run gen:types` from `src/tools/panel/openapi.json` - never hand-edit
  it. Hand-written DTOs alongside it are a temporary bridge and should shrink
  over time, not grow.
- **One mechanism per behaviour.** When two things can detect the same event -
  a service poll and a job poll both noticing a scan finished - keep one and
  delete the other. Two detectors for one edge is the frontend's version of two
  sources of truth: they drift, and the bug appears only in the timing gap.
- **Polling stops on a terminal state.** A `refetchInterval` that never returns
  `false` is a leak. Terminal statuses are `done` and `failed`; assert the stop
  in a test, not by watching the network tab.
- **Query keys live in the keys registry**, never inline. Invalidation is
  centralized in the same place, so a new consumer cannot forget one of the
  queries that must refresh.
- **Optimistic updates need their rollback.** Any mutation that flips local
  state before the server confirms must restore it on error, including the
  expected errors like `409 already scanning`.
- **The dictionaries stay parallel.** Every key added to `en.ts` is added to
  `de.ts` in the same change.
- **Checks:** `npm run lint`, `npm run build` (typecheck included) and
  `npm run test:coverage` all pass before the change is done.
