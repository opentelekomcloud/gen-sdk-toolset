"""Narrow scanner diagnostics down to documentation errors.

Every rule here was measured on the panel dump of 2026-11-09 against the
manual review of each diagnostic (``tasks/2026-11-17-local-scan-tz.md``,
section 4). A rule reads only the scan result: an issue's code, ``location``
and ``details``, plus the document it belongs to.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterator

from tools.scanner.parsers.docutils.patterns import EXAMPLE_HTTP_PREFIX_RE
from tools.shared.ir import Document, Endpoint, Example, Section, Service
from tools.shared.scan import Issue, IssueCode, RepositoryScanResult

from .finding import DocCheck, DocFinding

# Words a Type cell is compared against to spot a misspelt type. Only the
# longer ones take part: short words are too close to too many others.
_PRIMITIVES = (
    "string",
    "integer",
    "long",
    "boolean",
    "number",
    "float",
    "double",
    "object",
    "array",
    "date",
    "datetime",
    "timestamp",
)
_KNOWN_TYPE_WORDS = frozenset({*_PRIMITIVES, "int", "bool", "map"})

_TABLE_NUMBER_RE = re.compile(r"Table\s*\d+")
_REFERENCE_MARKER_RE = re.compile(r"[A-Z_]*REFERENCE")
_COLLECTION_PREFIX_RE = re.compile(r"(array|list|map|dict)", re.IGNORECASE)
_PLACEHOLDER_RE = re.compile(r"\{([^}?]+)\}")
_SEPARATORS_RE = re.compile(r"[\s_\-]")
_DIGITS_RE = re.compile(r"(\d+)")

_Rule = Callable[[str, str, Issue], DocFinding | None]


def find_doc_errors(result: RepositoryScanResult) -> list[DocFinding]:
    """Return the documentation errors in ``result``, sorted by place."""
    if not isinstance(result.repository, Service):
        return []
    findings: list[DocFinding] = []
    for document in result.repository.documents:
        findings.extend(_document_findings(document))
    return sorted(
        findings,
        # Top to bottom within a file; findings without a line go last.
        key=lambda f: (
            f.path,
            f.line is None,
            f.line or 0,
            f.section or "",
            _natural(f.location or ""),
            f.check.value,
        ),
    )


def _natural(value: str) -> tuple[tuple[int, int | str], ...]:
    """Sort key that puts "row 9" before "row 10"."""
    return tuple(
        (0, int(part)) if part.isdigit() else (1, part)
        for part in _DIGITS_RE.split(value)
        if part
    )


def _document_findings(document: Document) -> Iterator[DocFinding]:
    if not isinstance(document, Endpoint):
        return
    for section in document.sections:
        issues = section.scan_result.issues if section.scan_result else []
        yield from _invalid_json_findings(document.path, section, issues)
        for issue in issues:
            rule = _RULES.get(issue.code)
            if rule is None:
                continue
            finding = rule(document.path, section.name.value, issue)
            if finding is not None:
                yield finding
    # A parent typed "Table N" also leaves its child table without a parent
    # (nested_parent_not_found). Both come from the one Type cell, so only the
    # Type finding is reported; nested_parent_not_found has no rule of its own.


def _invalid_json_findings(
    path: str, section: Section, issues: list[Issue]
) -> Iterator[DocFinding]:
    """Pair each invalid-JSON issue with its example, in order.

    The issue's ``example N`` index restarts when examples are added to a
    section in more than one batch, so it cannot index ``section.examples``.
    Issues and unparsed JSON examples are emitted in the same order, so they
    are paired by position instead.
    """
    json_issues = [i for i in issues if i.code is IssueCode.EXAMPLE_INVALID_JSON]
    if not json_issues:
        return
    broken = [e for e in section.examples if e.parsed is None and _expects_json(e)]
    for position, issue in enumerate(json_issues):
        example = broken[position] if position < len(broken) else None
        if example is None:
            message = "Example is not valid JSON."
        else:
            error = _json_error(example)
            if error is None:
                # Valid JSON the parser does not keep: a scalar such as
                # null, true, 42 or "text". Not a documentation error.
                continue
            message = f"Example is not valid JSON: {error.msg}."
        yield DocFinding(
            check=DocCheck.INVALID_JSON,
            path=path,
            section=section.name.value,
            location=issue.location,
            message=message,
            line=issue.line,
        )


def _expects_json(example: Example) -> bool:
    if example.language:
        return example.language.lower() in {"json", "application/json"}
    return example.raw.lstrip().startswith(("{", "["))


def _json_error(example: Example) -> json.JSONDecodeError | None:
    candidate = EXAMPLE_HTTP_PREFIX_RE.sub("", example.raw, count=1).strip()
    try:
        json.loads(candidate)
    except json.JSONDecodeError as e:
        return e
    return None


def _type_finding(path: str, section: str, issue: Issue) -> DocFinding | None:
    value = (issue.details or "").strip()
    check, message = _classify_type(value)
    if check is None:
        return None
    return DocFinding(
        check=check,
        path=path,
        section=section,
        location=issue.location,
        message=message,
        line=issue.line,
    )


def _classify_type(value: str) -> tuple[DocCheck | None, str]:
    if _TABLE_NUMBER_RE.fullmatch(value):
        return DocCheck.TYPE_TABLE_NUMBER, (
            f"Type is a table reference (`{value}`) instead of a type. "
            "Use Object or Array of objects and keep the link to the table."
        )
    if _REFERENCE_MARKER_RE.fullmatch(value):
        return DocCheck.TYPE_REFERENCE_MARKER, (
            f"Type contains an internal marker (`{value}`) instead of a type."
        )
    suggestion = _near_primitive(value)
    if suggestion is not None:
        return DocCheck.TYPE_NEAR_PRIMITIVE, (
            f"Type `{value}` is not a known type. Did you mean `{suggestion}`?"
        )
    if _is_prose(value):
        return DocCheck.TYPE_PROSE, (
            f"Type column contains a description (`{value}`) instead of a type."
        )
    return None, ""


def _near_primitive(value: str) -> str | None:
    word = value.lower()
    if len(word) <= 3 or word in _KNOWN_TYPE_WORDS:
        return None
    for primitive in _PRIMITIVES:
        if _levenshtein(word, primitive) <= 2:
            return primitive
    return None


def _is_prose(value: str) -> bool:
    return (
        len(value.split()) >= 3
        and "<" not in value
        and ">" not in value
        and not _COLLECTION_PREFIX_RE.match(value)
    )


def _path_param_finding(path: str, section: str, issue: Issue) -> DocFinding | None:
    name = issue.location or ""
    placeholder = _misspelt_placeholder(name, issue.details or "")
    if placeholder is None:
        return None
    return DocFinding(
        check=DocCheck.PATH_PARAM_SPELLING,
        path=path,
        section=section,
        location=issue.location,
        message=(
            f"Parameter `{name}` does not match the path placeholder "
            f"`{{{placeholder}}}`."
        ),
        line=issue.line,
    )


def _misspelt_placeholder(name: str, uri: str) -> str | None:
    """The path placeholder ``name`` was most likely meant to be, if any."""
    normalized = _normalize(name)
    for placeholder in _PLACEHOLDER_RE.findall(uri.split("?", 1)[0]):
        if placeholder == name:
            continue
        candidate = _normalize(placeholder)
        if candidate == normalized or (
            len(candidate) > 4 and _levenshtein(normalized, candidate) <= 2
        ):
            return placeholder
    return None


def _normalize(value: str) -> str:
    return _SEPARATORS_RE.sub("", value.lower())


def _ref_page_finding(path: str, section: str, issue: Issue) -> DocFinding | None:
    anchor = issue.details or ""
    # Table anchors are "<page id>__<element id>"; a bare page id targets a page.
    if not anchor or "__" in anchor:
        return None
    return DocFinding(
        check=DocCheck.REF_WHOLE_PAGE,
        path=path,
        section=section,
        location=issue.location,
        message=(
            f"Field `{issue.location}` links to a whole page (`{anchor}`) "
            "instead of a table."
        ),
        line=issue.line,
    )


def _code_block_finding(path: str, section: str, issue: Issue) -> DocFinding | None:
    if not (issue.details or "").strip().startswith(".. code"):
        return None
    return DocFinding(
        check=DocCheck.EMPTY_CODE_BLOCK,
        path=path,
        section=section,
        location=issue.location,
        message="Empty or broken code-block directive.",
        line=issue.line,
    )


def _levenshtein(a: str, b: str) -> int:
    previous = list(range(len(b) + 1))
    for i, char_a in enumerate(a, start=1):
        current = [i]
        for j, char_b in enumerate(b, start=1):
            current.append(
                min(
                    previous[j] + 1,
                    current[j - 1] + 1,
                    previous[j - 1] + (char_a != char_b),
                )
            )
        previous = current
    return previous[-1]


_RULES: dict[IssueCode, _Rule] = {
    IssueCode.UNKNOWN_TYPE_FORMAT: _type_finding,
    IssueCode.PATH_PARAMETER_NOT_IN_URI: _path_param_finding,
    IssueCode.NESTED_REF_NOT_A_TABLE: _ref_page_finding,
    IssueCode.UNMAPPED_BLOCK: _code_block_finding,
}
