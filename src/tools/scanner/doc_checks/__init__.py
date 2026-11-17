"""Documentation errors the scanner can name with confidence.

Most scanner diagnostics mean "the scanner could not read this", which is as
often a scanner gap as a documentation defect. This package narrows a scan
result down to the cases that were measured to be documentation defects, so a
documentation author can be shown them without the scanner's own noise.
"""

from .checks import find_doc_errors
from .finding import DocCheck, DocFinding
from .markdown import render_markdown

__all__ = ["DocCheck", "DocFinding", "find_doc_errors", "render_markdown"]
