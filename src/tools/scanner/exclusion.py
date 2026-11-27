"""Decide which source paths are outside production coverage, and why.

Two passes, both pure. :func:`path_exclusion` needs only the path, so the
scanner applies it before fetching anything: a sample repository, a configured
segment (``calling_apis``, ``examples``, ...), or a directory whose name carries
a lifecycle label (``api_v1_to_be_discarded``). :func:`page_exclusion` reads a
fetched page for what its path does not show: an operation-wide notice ("This
API has been deprecated") or a lifecycle label in the title's parentheses.

Evidence that is there but not clearly about the whole operation - a
"deprecated" in prose, say - does not exclude the page. It stays counted and is
returned as a :class:`ReviewCandidate`, so a person decides.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Iterator, Mapping

from tools.scanner.parsers import extract_document_title
from tools.shared.scan import (
    ExcludedDocument,
    ExclusionEvidence,
    ExclusionReason,
    ReviewCandidate,
)

#: Where the evidence for a configured rule lives - the settings that hold it.
SEGMENTS_SETTING = "scanner.excluded_segments"
SAMPLE_REPOSITORIES_SETTING = "scanner.sample_repositories"

#: Lifecycle labels as the documentation writes them, keyed by their lower-case
#: words. A label marks the operation or section it is attached to for
#: retirement.
_LIFECYCLE_LABELS = {
    "to be discarded": "To Be Discarded",
    "discarded": "Discarded",
    "deprecated": "Deprecated",
    "outdated": "Outdated",
    "historical apis": "Historical APIs",
    "old version": "Old Version",
    "unavailable soon": "Unavailable Soon",
    "to be taken offline": "To Be Taken Offline",
}
#: Only a section is retired by "Not Recommended": an operation page saying so
#: usually points to a better call rather than withdrawing itself.
_SECTION_ONLY_LABELS = {"not recommended": "Not Recommended"}


def _label_pattern(labels: Mapping[str, str]) -> re.Pattern[str]:
    # Longest first, so "to be discarded" wins over "discarded".
    words = sorted(labels, key=len, reverse=True)
    return re.compile(r"\b(" + "|".join(re.escape(w) for w in words) + r")\b")


#: Every label's display form, whichever pattern matched it.
_LABEL_NAMES = _LIFECYCLE_LABELS | _SECTION_ONLY_LABELS
_SECTION_LABEL_RE = _label_pattern(_LABEL_NAMES)
_OPERATION_LABEL_RE = _label_pattern(_LIFECYCLE_LABELS)
_PARENTHESES_RE = re.compile(r"\(([^)]*)\)")
_REF_RE = re.compile(r":ref:`[^`]*`")
_CODE_DIRECTIVES = (".. code-block::", ".. code::", ".. sourcecode::")
#: A grid table's row opens and closes with "|"; its borders are "+---+" or
#: "+===+". A line block ("| text") or a "+" bullet is prose and stays.
_GRID_ROW_RE = re.compile(r"^\|.*\|$")
_GRID_BORDER_RE = re.compile(r"^\+[-=+]+\+$")

_SUBJECT = r"\bthis (?:api|interface|operation)(?: call)?"
_COMPATIBILITY = r"(?:backward )?compatibility(?: reasons)?"
#: A sentence about the operation itself that withdraws it or keeps it only
#: for compatibility ("This API call exists for compatibility reasons only and
#: is not meant to be used"). The subject must be the operation: "This
#: parameter is to be discarded" is about a field, and the operation stays.
#: "Unavailable" retires only when it is about the future and unqualified:
#: the sentence ends at "unavailable" or "unavailable soon". "This API is
#: unavailable in region X" or "will be unavailable during maintenance"
#: limits the operation rather than withdrawing it, and stays for review.
_SENTENCE_END = r"(?=\s*(?:[.;!]|$))"
_NOTICE_RE = re.compile(
    "|".join(
        [
            _SUBJECT + r" (?:has been|is|was|will be|will soon be|is to be|"
            r"is going to be) (?:deprecated|discarded|taken offline)\b",
            _SUBJECT
            + r" (?:will be|will soon be|is going to be) unavailable(?: soon)?"
            + _SENTENCE_END,
            _SUBJECT + r" is unavailable soon" + _SENTENCE_END,
            _SUBJECT + r" is no longer (?:available|supported|maintained)\b",
            _SUBJECT + r" is not meant to be used\b",
            _SUBJECT
            + r" (?:is|exists) (?:\w+ )?(?:only for "
            + _COMPATIBILITY
            + r"|for "
            + _COMPATIBILITY
            + r" only)\b",
        ]
    ),
    re.IGNORECASE,
)
#: Words that suggest a retirement without saying what retires. Seen outside a
#: notice, they make a page a review candidate rather than an exclusion.
_AMBIGUOUS_RE = re.compile(
    r"\b(?:deprecated|discarded|to be taken offline|no longer (?:available|supported)|"
    r"unavailable soon|not meant to be used|only for "
    + _COMPATIBILITY
    + r"|for "
    + _COMPATIBILITY
    + r" only)\b|"
    + _SUBJECT
    + r" (?:is|has been|was|will be|will soon be|is going to be) unavailable\b",
    re.IGNORECASE,
)


def path_exclusion(
    repo: str,
    path: str,
    *,
    segments: Mapping[str, ExclusionReason],
    sample_repositories: Collection[str],
) -> ExcludedDocument | None:
    """Return why ``path`` is excluded by its location alone, or ``None``.

    A sample repository wins over everything else, since nothing in it is a
    service. Otherwise the outermost directory that decides is the evidence:
    a configured segment, or a directory named with a lifecycle label.
    """
    if repo in sample_repositories:
        return ExcludedDocument(
            path=path,
            reason=ExclusionReason.sample,
            evidence=ExclusionEvidence(source=SAMPLE_REPOSITORIES_SETTING, text=repo),
        )

    *directories, _filename = path.split("/")
    for depth, segment in enumerate(directories):
        if segment in segments:
            return ExcludedDocument(
                path=path,
                reason=segments[segment],
                evidence=ExclusionEvidence(source=SEGMENTS_SETTING, text=segment),
            )
        label = _label_in(_words(segment), _SECTION_LABEL_RE)
        if label is not None:
            return ExcludedDocument(
                path=path,
                reason=ExclusionReason.retired,
                evidence=ExclusionEvidence(
                    source="/".join(directories[: depth + 1]), text=label
                ),
            )
    return None


def page_exclusion(
    path: str, content: str
) -> ExcludedDocument | ReviewCandidate | None:
    """Return what a fetched page says about its own lifecycle.

    An operation-wide notice is the strongest evidence and is looked for
    first; a lifecycle label in the title's parentheses ("Creating a Shared
    File System (Deprecated)") comes next. A retirement word anywhere else in
    prose only makes the page a review candidate. Tables and literal blocks
    are not read: a field's notice or an example body says nothing about the
    operation. Nor is the text of a ``:ref:`` link, which names another page:
    an index listing "Creating a Cluster (Discarded)" is not discarded itself.
    """
    lines = list(_prose_lines(content))

    for number, line in lines:
        if _NOTICE_RE.search(_without_links(line)):
            return _retired(path, number, line)

    title = extract_document_title(content)
    if title is not None:
        for inner in _PARENTHESES_RE.findall(title):
            if _label_in(inner.lower(), _OPERATION_LABEL_RE) is not None:
                # Looked up in the raw lines the title was read from, not in the
                # prose: a title that opens with a substitution ("|br| ...") is
                # not prose, but it is still this page's title.
                raw = content.splitlines()
                number = next(
                    n for n, line in enumerate(raw, 1) if line.rstrip() == title
                )
                return _retired(path, number, title)

    for number, line in lines:
        if _AMBIGUOUS_RE.search(_without_links(line)):
            return ReviewCandidate(
                path=path,
                evidence=ExclusionEvidence(source=path, line=number, text=line),
            )
    return None


def _without_links(line: str) -> str:
    return _REF_RE.sub("", line)


def _retired(path: str, line: int, text: str) -> ExcludedDocument:
    return ExcludedDocument(
        path=path,
        reason=ExclusionReason.retired,
        evidence=ExclusionEvidence(source=path, line=line, text=text),
    )


def _words(segment: str) -> str:
    return re.sub(r"[-_]+", " ", segment).lower()


def _label_in(words: str, pattern: re.Pattern[str]) -> str | None:
    match = pattern.search(words)
    return None if match is None else _LABEL_NAMES[match.group(1)]


def _opens_literal_block(stripped: str) -> bool:
    # ".. note::" and ".. important::" end in "::" too, but their body is prose
    # - the very place a notice lives. Only code directives and a paragraph
    # ending in "::" introduce text that is shown as written.
    if stripped.startswith(".. "):
        return stripped.startswith(_CODE_DIRECTIVES)
    return stripped.endswith("::")


def _prose_lines(content: str) -> Iterator[tuple[int, str]]:
    """Yield ``(line number, stripped line)`` for lines a reader sees as prose.

    Grid-table rows and the bodies of literal blocks (a paragraph ending in
    ``::``, ``.. code-block::``) are skipped; a block ends at the first
    non-blank line indented no deeper than the line that opened it.
    """
    block_indent: int | None = None
    for number, raw in enumerate(content.splitlines(), start=1):
        stripped = raw.strip()
        if not stripped:
            continue
        indent = len(raw) - len(raw.lstrip())
        if block_indent is not None:
            if indent > block_indent:
                continue
            block_indent = None
        if _opens_literal_block(stripped):
            block_indent = indent
        if _GRID_ROW_RE.match(stripped) or _GRID_BORDER_RE.match(stripped):
            continue
        yield number, stripped
