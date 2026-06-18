"""Pin down where Sphinx ``:ref:`` markup is resolved .

The passthrough role registered by :func:`DocutilsParser._ensure_roles`
resolves ``:ref:`Label <anchor>``` to its visible label *at docutils parse
time*, so table cells already arrive without any ``:ref:`` markup. This test
guards that contract; ``table.py`` therefore does no ``:ref:`` stripping of
its own.
"""

from __future__ import annotations

from docutils import nodes
from docutils.core import publish_doctree

from tools.infrastructure.parsers.docutils.doc_parser import _ensure_roles
from tools.infrastructure.parsers.docutils.table import extract_parameter_table

_RST = """
Demo
====

Request
-------

.. table:: Request body parameters

   ===========================  ============================  ===========
   Parameter                    Type                          Description
   ===========================  ============================  ===========
   :ref:`proto <anchor_proto>`  :ref:`Object <anchor_obj>`    some desc
   ===========================  ============================  ===========
"""


def _first_table(doctree: nodes.document) -> nodes.table:
    return next(iter(doctree.findall(nodes.table)))


def test_ref_resolved_at_parse_time() -> None:
    """A `:ref:` cell arrives at extract_parameter_table already as its label."""
    _ensure_roles()
    doctree = publish_doctree(_RST, settings_overrides={"report_level": 5})

    table = _first_table(doctree)
    body_cell = next(iter(table.findall(nodes.tbody))).findall(nodes.row)
    first_cell = list(next(iter(body_cell)).children)[0]
    assert ":ref:" not in first_cell.astext()
    assert first_cell.astext() == "proto"

    # And end-to-end: the extracted Parameter carries the clean label/type,
    # with no stripping done inside table.py.
    extraction = extract_parameter_table(table)
    assert extraction.parameters[0].name == "proto"
    assert extraction.parameters[0].param_type.value == "Object"
