"""Reconcile URI placeholders with documented path-parameter tables."""

from __future__ import annotations

from tools.shared.ir import Parameter, ParameterType, SectionName
from tools.shared.scan import Issue, IssueCode

from .patterns import URI_PLACEHOLDER_RE
from .table import TableExtraction, TableRow


def reconcile_path_parameters(
    uri: str,
    primary_tables: dict[SectionName, TableExtraction],
) -> list[Issue]:
    placeholders = list(dict.fromkeys(URI_PLACEHOLDER_RE.findall(uri)))
    source = primary_tables.get(SectionName.PATH_PARAMS)
    if source is None and not placeholders:
        return []

    documented = (
        {parameter.name: parameter for parameter in source.parameters} if source else {}
    )
    primary_tables[SectionName.PATH_PARAMS] = _path_extraction(
        placeholders,
        documented,
        source,
    )
    return _path_parameter_issues(uri, placeholders, documented)


def _path_extraction(
    placeholders: list[str],
    documented: dict[str, Parameter],
    source: TableExtraction | None,
) -> TableExtraction:
    parameters = [
        Parameter(
            name=name,
            param_type=ParameterType.STRING,
            mandatory=True,
            description=documented[name].description if name in documented else "",
        )
        for name in placeholders
    ]
    return TableExtraction(
        rows=[TableRow(parameter) for parameter in parameters],
        issues=(
            [
                issue
                for issue in source.issues
                if issue.code is not IssueCode.UNKNOWN_TYPE_FORMAT
            ]
            if source
            else []
        ),
        fields_total=len(parameters),
        fields_recognized=len(parameters),
        fields_unknown_type=0,
        fields_failed=0,
    )


def _path_parameter_issues(
    uri: str,
    placeholders: list[str],
    documented: dict[str, Parameter],
) -> list[Issue]:
    placeholder_names = set(placeholders)
    return [
        Issue(
            code=IssueCode.PATH_PARAMETER_NOT_IN_URI,
            location=name,
            details=uri,
        )
        for name in documented
        if name not in placeholder_names
    ]
