---
name: plan
description: Write an implementation plan for a task in this project's established format, before any code is written.
argument-hint: "[issue number or task description]"
disable-model-invocation: true
---

Write an implementation plan for: `$ARGUMENTS`

If an issue number was given, read it first (`gh issue view <n>`). If `gh` is
not installed, ask for the issue text rather than guessing what it says. Read the code
you are about to change before planning changes to it - a plan built on a guess
about the current state wastes more time than it saves.

Use this structure. It is the format this project already uses, and keeping it
identical is the point: two people planning in the same shape produce code in
the same shape.

## 1. What already exists

What is already in place that this task can build on, with file references.
Explicitly list scope items that turn out to be **already done** and need
verification rather than new code. This section exists to stop the plan from
rebuilding something that is there.

## 2. Scope

**In scope** - a numbered list of what this slice delivers.

**Deferred** - what is deliberately left for a follow-up, each with its issue
number. Anything listed here must end up either as a `TODO(#N)` or a
`NotImplementedError("... see #N")` in the code, because the plan itself is not
committed and the issue number is the only link that survives.

## 3. Files to add and change

A tree with a one-line note per file: `NEW`, `CHANGE`, or `MOVED`.

## 4. Component design

Per component: the shape it takes, a code sketch of the signature or the model,
and *why this shape* - the constraint that rules out the obvious alternative.
Record the decisions that were made along the way, so nobody re-litigates them.

## 5. Data flow

The path a request or a record takes through the new code, end to end.

## 6. Testing plan

Which tests, against which fixtures, and what each one proves. Include the
reachability test for any new status or issue code. Note the checks to run:
`ruff check`, `lint-imports`, `pytest`, coverage gates.

## 7. Step-by-step checklist

The order to implement in, each step independently verifiable.

Finish by re-reading the plan for over-engineering: injection seams a
`monkeypatch` would cover, abstractions with a single implementation, parameters
that will always receive the same value. Cut them in the plan, where it is free,
rather than in review.
