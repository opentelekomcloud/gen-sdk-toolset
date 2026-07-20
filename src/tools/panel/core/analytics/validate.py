"""Flag documentation defects by comparing documented tables against examples.

Counterpart to :mod:`assemble`: instead of silently rebuilding nesting from an
example, this reports where the documentation and the example disagree. The
canonical case is a request/response whose wrapper object is proven only by the
example while the tables list the fields flat — i.e. the nesting is undocumented.

Pure and non-mutating: it derives issues from the scan-result IR. Nothing here
is stored by the scanner; it is a computed view, like the status roll-ups.
"""

from __future__ import annotations

from tools.shared.ir import Endpoint, SectionName
from tools.shared.scan import Issue, IssueCode

from .assemble import _PROOF_SECTIONS, example_root


def example_documentation_issues(
    endpoint: Endpoint,
) -> dict[SectionName, list[Issue]]:
    """Return per-section documentation issues implied by the parsed examples.

    Currently detects :data:`IssueCode.NESTING_ONLY_IN_EXAMPLE`: the example
    wraps its fields under a root object that the documentation tables never
    define as a field, or defines as a field but lists the children flatly.

    :param endpoint: The scanned endpoint IR to validate.
    """
    sections = {section.name: section for section in endpoint.sections}
    found: dict[SectionName, list[Issue]] = {}
    for parameter_name, example_name in _PROOF_SECTIONS.items():
        section = sections.get(parameter_name)
        example_section = sections.get(example_name)
        if section is None or example_section is None:
            continue
            
        issues = _validate_section_nesting(section, example_section)
        if issues:
            found[parameter_name] = issues
            
    return found


def _validate_section_nesting(
    section: Section, example_section: Section
) -> list[Issue]:
    parsed_examples = [
        example.parsed for example in example_section.examples if example.parsed
    ]
    root = example_root(parsed_examples)
    if root is None:
        return []
        
    root_name, _fields = root
    documented = {parameter.name for parameter in section.parameters}
    
    if root_name not in documented:
        return _check_missing_wrapper(root_name)

    return _check_flattened_siblings(section.parameters, root_name, _fields)


def _check_missing_wrapper(root_name: str) -> list[Issue]:
    return [
        Issue(
            code=IssueCode.NESTING_ONLY_IN_EXAMPLE,
            location=root_name,
            details=(
                f"example wraps fields under '{root_name}', but the "
                "documentation tables do not define it as a field"
            ),
        )
    ]


def _check_flattened_siblings(
    parameters: list, root_name: str, _fields: set[str]
) -> list[Issue]:
    root_param = next(p for p in parameters if p.name == root_name)
    if not root_param.children:
        siblings = [
            p for p in parameters if p.name != root_name and p.name in _fields
        ]
        if siblings:
            return [
                Issue(
                    code=IssueCode.NESTING_ONLY_IN_EXAMPLE,
                    location=root_name,
                    details=(
                        f"example wraps fields under '{root_name}', but the "
                        "documentation tables list them as flat siblings"
                    ),
                )
            ]
    return []
