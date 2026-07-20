"""Post-hoc analytics over a scan result (pure, no scanner/HTTP dependencies).

These functions operate on the already-extracted IR (``Endpoint`` and its
sections) rather than on scanner internals. They are the panel-side home for
derived views over a scan: comparing the documented tables against the parsed
examples (:mod:`validate`) and, on demand, rebuilding the nesting the examples
prove (:mod:`assemble`).
"""

from __future__ import annotations

from .assemble import assemble_nesting_from_examples
from .validate import example_documentation_issues

__all__ = [
    "assemble_nesting_from_examples",
    "example_documentation_issues",
]
