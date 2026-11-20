"""Extract examples from docutils nodes and assemble example sections."""

from __future__ import annotations

import json
from typing import NamedTuple

from docutils import nodes

from tools.shared.ir import Example, Section, SectionName
from tools.shared.scan import Issue, IssueCode, SectionScanResult, SectionStatus

from .diagnostics import ISSUE_DETAILS_MAX
from .patterns import EXAMPLE_HTTP_PREFIX_RE
from .source_lines import block_start_line
from .types import SectionKind

#: JSON errors the parser reports at the token after the missing delimiter,
#: which is often on the next line.
_DELIMITER_ERRORS = frozenset({"Expecting ',' delimiter", "Expecting ':' delimiter"})


class ExampleBlock(NamedTuple):
    """An example with its block's start line, until its issues are built.

    ``Example`` is a contract and carries no line; the issue does.
    """

    example: Example
    start_line: int | None = None


def process_example_section(
    section_node: nodes.section,
    kind: SectionKind,
    sections: dict[SectionName, Section],
) -> None:
    blocks = extract_examples(section_node)

    if kind is SectionKind.EXAMPLE_REQUEST:
        add_examples_to_section(sections, SectionName.EXAMPLE_REQUEST, blocks)
        return
    if kind is SectionKind.EXAMPLE_RESPONSE:
        add_examples_to_section(sections, SectionName.EXAMPLE_RESPONSE, blocks)
        return

    request, response, issues = split_combined_examples(blocks)
    if request:
        add_examples_to_section(
            sections,
            SectionName.EXAMPLE_REQUEST,
            request,
            extra_issues=issues,
        )
    if response:
        add_examples_to_section(sections, SectionName.EXAMPLE_RESPONSE, response)


_LABELLED_OWNER = {
    "request": SectionName.EXAMPLE_REQUEST,
    "response": SectionName.EXAMPLE_RESPONSE,
}


def labelled_example_owner(
    block: nodes.literal_block,
) -> tuple[SectionName, str] | None:
    """Return the example section a run-in label puts this block in.

    Style-A documents converted from HTML often write their examples inside the
    Request or Response heading, announced by a bold paragraph
    (``**Example response**:``) instead of a heading of their own. The label is
    what makes the block an example; a block with no such label is left alone,
    so a URI snippet never becomes an example by accident.

    :param block: The literal block to place.
    """
    if block.parent is None:
        return None
    index = block.parent.index(block) - 1
    while index >= 0:
        sibling = block.parent[index]
        if isinstance(sibling, nodes.paragraph):
            text = sibling.astext().strip()
            if not _is_example_label(text):
                return None
            normalized = text.lower()
            for keyword, name in _LABELLED_OWNER.items():
                if keyword in normalized:
                    return name, text
            return None
        index -= 1
    return None


def inside_table(node: nodes.Element) -> bool:
    """True when this node sits inside a parameter table.

    A description cell routinely holds a literal block - an injected script, a
    pattern, a sample value. Its text is already extracted as part of the
    parameter, so the block is neither an example nor unread; treating it as
    either invents a diagnostic about content we did read.

    :param node: The node to place.
    """
    parent = node.parent
    while parent is not None:
        if isinstance(parent, nodes.table):
            return True
        parent = parent.parent
    return False


def process_inline_examples(
    section_node: nodes.section,
    sections: dict[SectionName, Section],
) -> list[nodes.literal_block]:
    """Extract the blocks this section labels as examples; return the rest.

    The returned blocks are the ones nothing consumed - the caller reports them
    so that "we did not read this" never passes for "there was nothing here".
    Blocks inside a parameter table are not among them: the table already
    consumed their text.

    :param section_node: A request or response section node.
    :param sections: The sections collected so far, extended in place.
    """
    leftover: list[nodes.literal_block] = []
    for block in section_node.findall(nodes.literal_block):
        if inside_table(block):
            continue
        placed = labelled_example_owner(block)
        if placed is None:
            leftover.append(block)
            continue
        name, label = placed
        add_examples_to_section(sections, name, [_make_example(block, label=label)])
    return leftover


def extract_examples(section: nodes.section) -> list[ExampleBlock]:
    """Return every code or literal block inside a section."""
    visited: set[int] = set()
    blocks = _extract_from_lists(section, visited)
    blocks.extend(_extract_sequential(section, visited))
    return blocks


def _extract_from_lists(
    section: nodes.section, visited: set[int]
) -> list[ExampleBlock]:
    blocks: list[ExampleBlock] = []
    for item in section.findall(nodes.list_item):
        label = _extract_item_label(item)
        for code in item.findall(nodes.literal_block):
            if id(code) in visited:
                continue
            visited.add(id(code))
            blocks.append(_make_example(code, label=label))
    return blocks


def _extract_sequential(
    section: nodes.section, visited: set[int]
) -> list[ExampleBlock]:
    blocks: list[ExampleBlock] = []
    current_label: str | None = None
    for node in section.findall(nodes.Element):
        if isinstance(node, nodes.paragraph):
            text = node.astext().strip()
            if _is_example_label(text):
                current_label = text
        elif isinstance(node, nodes.literal_block) and id(node) not in visited:
            visited.add(id(node))
            blocks.append(_make_example(node, label=current_label))
    return blocks


def split_combined_examples(
    blocks: list[ExampleBlock],
) -> tuple[list[ExampleBlock], list[ExampleBlock], list[Issue]]:
    request: list[ExampleBlock] = []
    response: list[ExampleBlock] = []
    guessed = False

    for block in blocks:
        label = (block.example.label or "").lower()
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
    blocks: list[ExampleBlock],
    *,
    extra_issues: list[Issue] | None = None,
) -> None:
    if not blocks:
        return

    issues = [*_example_json_issues(blocks), *(extra_issues or [])]
    examples = [block.example for block in blocks]
    existing = sections.get(name)
    if existing is not None:
        _extend_example_section(existing, examples, issues)
        return

    sections[name] = _create_example_section(name, examples, issues)


def _extract_item_label(item: nodes.list_item) -> str | None:
    paragraph = next(iter(item.findall(nodes.paragraph)), None)
    if paragraph is None:
        return None
    text = paragraph.astext().strip()
    return text or None


def _is_example_label(text: str) -> bool:
    normalized = text.lower()
    return ("example" in normalized or "sample" in normalized) and (
        "request" in normalized or "response" in normalized
    )


def _make_example(block: nodes.literal_block, *, label: str | None) -> ExampleBlock:
    raw = block.astext()
    example = Example(
        raw=raw,
        language=_extract_language(block),
        parsed=_try_parse_json(raw),
        label=label,
    )
    return ExampleBlock(example, block_start_line(block))


def _extract_language(block: nodes.literal_block) -> str | None:
    language = block.get("language")
    if language:
        return language
    return next(
        (name for name in block.get("classes", []) if name != "code"),
        None,
    )


def json_candidate(raw: str) -> tuple[str, int]:
    """The text tried as JSON, and how many lines of ``raw`` precede it.

    A leading HTTP request line is dropped, then surrounding whitespace.
    """
    without_prefix = EXAMPLE_HTTP_PREFIX_RE.sub("", raw, count=1)
    start = len(raw) - len(without_prefix.lstrip())
    return raw[start:].rstrip(), raw.count("\n", 0, start)


def _try_parse_json(raw: str) -> dict | list | None:
    candidate, _ = json_candidate(raw)
    if not candidate:
        return None
    try:
        result = json.loads(candidate)
    except (json.JSONDecodeError, ValueError):
        return None
    if isinstance(result, (dict, list)):
        return result
    return None


def _example_json_issues(blocks: list[ExampleBlock]) -> list[Issue]:
    return [
        Issue(
            code=IssueCode.EXAMPLE_INVALID_JSON,
            location=f"example {index}",
            details=(block.example.label or "")[:ISSUE_DETAILS_MAX] or None,
            line=_json_error_line(block),
        )
        for index, block in enumerate(blocks, start=1)
        if block.example.parsed is None and expects_json(block.example)
    ]


def _json_error_line(block: ExampleBlock) -> int | None:
    """RST line of the JSON error in ``block``.

    For a missing delimiter the JSON parser stops at the next token, often on
    the next line, while the delimiter belongs right after the previous one. A
    scalar parses but is still flagged, since ``parsed`` keeps only objects and
    arrays; it gets the block's first line.
    """
    if block.start_line is None:
        return None
    candidate, skipped = json_candidate(block.example.raw)
    try:
        json.loads(candidate)
    except json.JSONDecodeError as error:
        position = error.pos
        if error.msg in _DELIMITER_ERRORS:
            position = len(candidate[:position].rstrip()) - 1
        return block.start_line + skipped + candidate.count("\n", 0, max(position, 0))
    return block.start_line


def expects_json(example: Example) -> bool:
    """True when the example is meant to be JSON.

    The language says so when the block declares one; otherwise the first
    character does.
    """
    if example.language:
        return example.language.lower() in {"json", "application/json"}
    return example.raw.lstrip().startswith(("{", "["))


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
