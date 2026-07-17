"""Extract examples from docutils nodes and assemble example sections."""

from __future__ import annotations

import json

from docutils import nodes

from tools.shared.ir import Example, Section, SectionName
from tools.shared.scan import Issue, IssueCode, SectionScanResult, SectionStatus

from .patterns import HTTP_PREFIX_RE
from .table import DETAILS_MAX


def extract_examples(section: nodes.section) -> list[Example]:
    """Return every code or literal block inside a section."""
    blocks: list[Example] = []
    visited: set[int] = set()

    for item in section.findall(nodes.list_item):
        label = _extract_item_label(item)
        for code in item.findall(nodes.literal_block):
            if id(code) in visited:
                continue
            visited.add(id(code))
            blocks.append(_make_example(code, label=label))

    for code in section.findall(nodes.literal_block):
        if id(code) in visited:
            continue
        visited.add(id(code))
        blocks.append(_make_example(code, label=None))

    return blocks


def split_combined_examples(
    blocks: list[Example],
) -> tuple[list[Example], list[Example], list[Issue]]:
    request: list[Example] = []
    response: list[Example] = []
    guessed = False

    for block in blocks:
        label = (block.label or "").lower()
        if "response" in label:
            response.append(block)
        else:
            request.append(block)
            guessed = guessed or "request" not in label

    issues = []
    if guessed:
        issues.append(
            Issue(
                code=IssueCode.EXAMPLE_UNLABELED,
                location="combined example section",
                details="request/response split guessed (no labels)",
            )
        )
    return request, response, issues


def add_examples_to_section(
    sections: dict[SectionName, Section],
    name: SectionName,
    blocks: list[Example],
    *,
    extra_issues: list[Issue] | None = None,
) -> None:
    if not blocks:
        return

    issues = [*_example_json_issues(blocks), *(extra_issues or [])]
    existing = sections.get(name)
    if existing is not None:
        _extend_example_section(existing, blocks, issues)
        return

    sections[name] = _create_example_section(name, blocks, issues)


def _extract_item_label(item: nodes.list_item) -> str | None:
    p = next(iter(item.findall(nodes.paragraph)), None)
    if p is None:
        return None
    text = p.astext().strip()
    return text or None


def _make_example(block: nodes.literal_block, *, label: str | None) -> Example:
    raw = block.astext()
    return Example(
        raw=raw,
        language=_extract_language(block),
        parsed=_try_parse_json(raw),
        label=label,
    )


def _extract_language(block: nodes.literal_block) -> str | None:
    language = block.get("language")
    if language:
        return language
    return next(
        (name for name in block.get("classes", []) if name != "code"),
        None,
    )


def _try_parse_json(raw: str) -> dict | list | None:
    candidate = HTTP_PREFIX_RE.sub("", raw, count=1).strip()
    if not candidate:
        return None
    try:
        result = json.loads(candidate)
    except (json.JSONDecodeError, ValueError):
        return None
    if isinstance(result, (dict, list)):
        return result
    return None


def _example_json_issues(blocks: list[Example]) -> list[Issue]:
    return [
        Issue(
            code=IssueCode.EXAMPLE_INVALID_JSON,
            location=f"example {index}",
            details=(block.label or "")[:DETAILS_MAX] or None,
        )
        for index, block in enumerate(blocks, start=1)
        if block.parsed is None and _expects_json(block)
    ]


def _expects_json(block: Example) -> bool:
    if block.language:
        return block.language.lower() in {"json", "application/json"}
    return block.raw.lstrip().startswith(("{", "["))


def _create_example_section(
    name: SectionName,
    blocks: list[Example],
    issues: list[Issue],
) -> Section:
    status = SectionStatus.PARTIAL if _has_invalid_example(issues) else SectionStatus.OK
    return Section(
        name=name,
        examples=list(blocks),
        scan_result=SectionScanResult(status=status, issues=issues),
    )


def _extend_example_section(
    section: Section,
    blocks: list[Example],
    issues: list[Issue],
) -> None:
    section.examples.extend(blocks)
    section.scan_result.issues.extend(issues)
    if _has_invalid_example(section.scan_result.issues):
        section.scan_result.status = SectionStatus.PARTIAL


def _has_invalid_example(issues: list[Issue]) -> bool:
    return any(issue.code is IssueCode.EXAMPLE_INVALID_JSON for issue in issues)
