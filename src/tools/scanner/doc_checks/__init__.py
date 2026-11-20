"""Documentation errors the scanner can name with confidence.

Most scanner diagnostics mean "the scanner could not read this", which is as
often a scanner gap as a documentation defect. A documentation author is shown
only the cases that are defects in the page, so that a report full of the
scanner's own gaps does not teach them to ignore it.
"""

from .checks import find_doc_errors
from .finding import DocCheck, DocFinding
from .markdown import render_markdown

__all__ = ["DocCheck", "DocFinding", "find_doc_errors", "render_markdown"]
