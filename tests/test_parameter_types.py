from docutils import nodes
from docutils.core import publish_doctree

from tools.scanner.parsers.docutils.table import extract_parameter_table
from tools.shared.ir import ParameterType


def test_legacy_otc_parameter_types() -> None:
    doctree = publish_doctree(
        """
=================== =================== ===========
Name                Type                Description
=================== =================== ===========
configuration       Data structure      Settings
items               List data structure Nested items
period_start_date   Long integer        Start time
=================== =================== ===========
"""
    )
    table = next(iter(doctree.findall(nodes.table)))

    extraction = extract_parameter_table(table)

    assert [parameter.param_type for parameter in extraction.parameters] == [
        ParameterType.OBJECT,
        ParameterType.ARRAY_OF_OBJECTS,
        ParameterType.LONG,
    ]
    assert [parameter.type_name for parameter in extraction.parameters] == [
        None,
        None,
        None,
    ]
    assert extraction.fields_recognized == 3
    assert extraction.fields_unknown_type == 0
