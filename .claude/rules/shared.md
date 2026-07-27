---
description: Contract discipline for the shared IR and scan models
paths:
  - "src/tools/shared/**"
---

`shared` is the contract layer. The panel, the frontend and any downstream
consumer read what is defined here, so a change is a published change.

- **Leaf module.** `shared` imports nothing internal - not from `scanner`, not
  from `panel`. `lint-imports` enforces this. If something here needs GitHub, Postgres or
  FastAPI, it belongs in another layer.
- **`extra="forbid"` on every model.** An unexpected key means the contract
  moved; failing is correct.
- **Invariants live in validators.** Uniqueness of section names, the field
  counter reconciliation, the mutual exclusion of `error` and `interruption` -
  all of these are enforced in `@model_validator`, not by callers remembering.
- **Adding or renaming a field changes the wire format.** Say so in the PR, and
  consider `DOCUMENT_SCHEMA_VERSION`. During the MVP the versions stay put, but
  the decision must be explicit rather than skipped.
- **Polymorphism survives JSON only through `kind`.** `Service` restores
  `Endpoint` subclasses in a `field_validator`, and `RepositoryScanResult`
  restores `Service`. If you add a subclass, add its restoration too, and add a
  round-trip test - this failure mode is silent: you get a base-class instance
  with no error at all.
- **The deferred export in `scan/__init__.py` is deliberate.** It exists to keep
  a single public facade without an import cycle between IR and repository-level
  results. Do not "simplify" it into a plain import without running the tests.

New names go into `docs/GLOSSARY.md` in the same change.
