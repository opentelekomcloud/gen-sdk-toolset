---
description: Design decision notes are read-only
paths:
  - "docs/council/**"
---

`docs/council/` holds the decisions behind tasks: IDEA → OQ → PRO → ADR → OUT
notes, one file each. One maintainer produces them outside the repository, so
everything here is read-only. How to read the chain is in README.md, "Design
decisions"; the prefixes are in `docs/GLOSSARY.md`, "Design notes".

- **Do not add, edit, rename or delete a note,** not even to fix a typo. The
  next export would drop or conflict with the change. Report the problem on the
  task's issue.
- **An ADR binds the implementation.** If the code, the issue or what you find
  while working contradicts an ADR or an outcome, stop and raise it on the issue.
  Do not decide around it in code.
- **The note file wins over the copy.** An issue quotes the ADR text; when the
  two differ, the file here is the source.
