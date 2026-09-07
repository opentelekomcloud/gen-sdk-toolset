"""Status codes as an endpoint section of their own.

Covers the three layouts the corpus contains - a two-column grid, a
three-column simple table, and a bare table with no title - through the table
parser and then end to end through the document parser.
"""

from __future__ import annotations

import pytest
from docutils import nodes
from docutils.core import publish_doctree

from tools.scanner.parsers import DocutilsParser
from tools.scanner.parsers.docutils.context import ensure_roles
from tools.scanner.parsers.docutils.status_code import extract_status_code_table
from tools.shared.ir import Section, SectionName, StatusCode
from tools.shared.scan import IssueCode, SectionStatus


@pytest.fixture
def parser() -> DocutilsParser:
    return DocutilsParser()


def _table(rst: str) -> nodes.table:
    ensure_roles()
    doctree = publish_doctree(rst, settings_overrides={"report_level": 5})
    return next(iter(doctree.findall(nodes.table)))


def _sections(parsed) -> dict:
    return {section.name: section for section in parsed.sections}


def _status_codes(parsed) -> Section:
    return _sections(parsed)[SectionName.STATUS_CODES]


# --------------------------------------------------------------------------- #
# The layouts, through the table parser
# --------------------------------------------------------------------------- #
GRID = """
+-------------+---------------------------------------+
| Status Code | Description                           |
+=============+=======================================+
| 200         | Information is successfully updated.  |
+-------------+---------------------------------------+
"""

WITH_REASON_PHRASE = """
=========== ====== ===============================
Status Code Status Description
=========== ====== ===============================
200         OK     Request processed successfully.
=========== ====== ===============================
"""

API_SPECIFIC = """
=========== =============================
Status Code Description
=========== =============================
200         The request is successful.
400         The request body is abnormal.
500         The system is abnormal.
=========== =============================
"""


def test_a_two_column_grid_table_is_read() -> None:
    extraction = extract_status_code_table(_table(GRID))

    assert extraction.issues == []
    assert extraction.codes == [
        StatusCode(code="200", description="Information is successfully updated.")
    ]


def test_a_reason_phrase_column_does_not_displace_the_description() -> None:
    """`Status Code | Status | Description` puts "OK" between the two columns
    the IR keeps. The description has to come from the description column, not
    from whichever cell happens to sit next to the code."""
    extraction = extract_status_code_table(_table(WITH_REASON_PHRASE))

    assert extraction.issues == []
    assert extraction.codes == [
        StatusCode(code="200", description="Request processed successfully.")
    ]


def test_an_api_specific_list_keeps_every_row() -> None:
    extraction = extract_status_code_table(_table(API_SPECIFIC))

    assert extraction.issues == []
    assert [code.code for code in extraction.codes] == ["200", "400", "500"]
    assert extraction.codes[1].description == "The request body is abnormal."


def test_a_table_whose_columns_are_unreadable_is_reported() -> None:
    """No code column means no status codes. Returning an empty list quietly
    would make an unreadable table indistinguishable from an absent one."""
    extraction = extract_status_code_table(
        _table(
            """
========= ===========
Something Description
========= ===========
whatever  text
========= ===========
"""
        )
    )

    assert extraction.codes == []
    (issue,) = extraction.issues
    assert issue.code is IssueCode.UNEXPECTED_COLUMNS
    assert "Something" in issue.details


def test_a_table_with_no_header_row_is_reported_not_read() -> None:
    """Without a header there is nothing to identify the columns by, and the
    first row is data. Guessing that column one holds codes would invent a
    reading of a table the document never labelled."""
    extraction = extract_status_code_table(
        _table(
            """
=====  =====
200    ok
400    bad
=====  =====
"""
        )
    )

    assert extraction.codes == []
    (issue,) = extraction.issues
    assert issue.code is IssueCode.UNEXPECTED_COLUMNS
    assert "(no header row)" in issue.details


def test_a_row_without_a_code_is_reported_rather_than_dropped() -> None:
    # A grid table, because a simple table cannot express an empty leading
    # cell - there it would mean "continues the row above".
    extraction = extract_status_code_table(
        _table(
            """
+-------------+-----------------------------+
| Status Code | Description                 |
+=============+=============================+
| 200         | The request is successful.  |
+-------------+-----------------------------+
|             | An orphan description.      |
+-------------+-----------------------------+
"""
        )
    )

    assert [code.code for code in extraction.codes] == ["200"]
    (issue,) = extraction.issues
    assert issue.code is IssueCode.MALFORMED_GRID_TABLE
    assert issue.location == "row 2"


# --------------------------------------------------------------------------- #
# End to end, on the real fixtures
# --------------------------------------------------------------------------- #
def test_a_page_local_success_code_table_is_parsed(
    parser: DocutilsParser, cce_doc: str
) -> None:
    section = _status_codes(parser.parse(cce_doc, "cce.rst"))

    assert section.scan_result.status is SectionStatus.OK
    assert [(c.code, c.description) for c in section.status_codes] == [
        ("200", "Information about the specified node is successfully updated.")
    ]


def test_a_status_table_with_a_reason_phrase_column_is_parsed(
    parser: DocutilsParser, kms_doc: str
) -> None:
    section = _status_codes(parser.parse(kms_doc, "kms.rst"))

    assert section.scan_result.status is SectionStatus.OK
    assert [(c.code, c.description) for c in section.status_codes] == [
        ("200", "Request processed successfully.")
    ]


def test_an_api_specific_status_list_is_parsed(
    parser: DocutilsParser, iam_doc: str
) -> None:
    """A bare table under the heading, with no `.. table::` title of its own."""
    section = _status_codes(parser.parse(iam_doc, "iam.rst"))

    assert section.scan_result.status is SectionStatus.OK
    assert [c.code for c in section.status_codes] == ["200", "400", "401", "403", "500"]
    assert section.status_codes[3].description == "Access denied."


def test_status_codes_are_never_parameters(
    parser: DocutilsParser, iam_doc: str
) -> None:
    """They are carried in their own field. Landing in `parameters` would put
    rows with no type and no mandatory flag into the field counters, and the
    document's quality numbers are built from those."""
    section = _status_codes(parser.parse(iam_doc, "iam.rst"))

    assert section.parameters == []
    assert section.scan_result.fields_total == 0


def test_a_document_with_no_status_section_records_it_missing(
    parser: DocutilsParser, elb_list_doc: str
) -> None:
    section = _status_codes(parser.parse(elb_list_doc, "elb.rst"))

    assert section.scan_result.status is SectionStatus.MISSING
    assert section.status_codes == []


def test_a_heading_that_only_links_elsewhere_is_missing_not_failed(
    parser: DocutilsParser, anti_ddos_root_doc: str
) -> None:
    """This page has a Status Code heading holding one cross-reference to the
    shared status-code page and no table. Nothing failed - the page genuinely
    documents no codes of its own, and `failed` would blame the scanner for
    what the document does not contain."""
    section = _status_codes(parser.parse(anti_ddos_root_doc, "antiddos.rst"))

    assert section.scan_result.status is SectionStatus.MISSING
    assert section.scan_result.issues == []


def test_a_status_table_is_not_reported_as_unmapped(
    parser: DocutilsParser, cce_doc: str, kms_doc: str, iam_doc: str
) -> None:
    """The acceptance criterion in the issue: a known status-code layout must
    not be flagged merely for being a status-code table."""
    for content, name in ((cce_doc, "cce"), (kms_doc, "kms"), (iam_doc, "iam")):
        parsed = parser.parse(content, f"{name}.rst")
        codes = [
            issue.code
            for section in parsed.sections
            if section.scan_result is not None
            for issue in section.scan_result.issues
        ]
        assert IssueCode.UNMAPPED_TABLE not in codes, name


def test_a_status_table_written_inside_the_response_section_still_lands(
    parser: DocutilsParser,
) -> None:
    """Some pages put the status codes under Response rather than under a
    heading of their own. The table's title is what identifies it there."""
    content = (
        ":original_name: demo.html\n\nDemo\n====\n\nURI\n---\n\nPOST /v1/test\n\n"
        "Response\n--------\n\n"
        ".. table:: **Table 2** Status code\n\n"
        "   =========== =============================\n"
        "   Status Code Description\n"
        "   =========== =============================\n"
        "   201         Created.\n"
        "   =========== =============================\n"
    )

    section = _status_codes(parser.parse(content, "demo.rst"))

    assert [c.code for c in section.status_codes] == ["201"]
    assert section.scan_result.status is SectionStatus.OK


def test_an_unreadable_status_table_fails_the_section(parser: DocutilsParser) -> None:
    """The other half of the guarantee. A table we could not read leaves the
    section `failed` and says why - not `missing`, which would claim the page
    documents no status codes when in truth we could not read the ones it has.
    """
    content = (
        ":original_name: demo.html\n\nDemo\n====\n\nURI\n---\n\nPOST /v1/test\n\n"
        "Status Codes\n------------\n\n"
        "========= ===========\n"
        "Something Description\n"
        "========= ===========\n"
        "whatever  text\n"
        "========= ===========\n"
    )

    section = _status_codes(parser.parse(content, "demo.rst"))

    assert section.scan_result.status is SectionStatus.FAILED
    assert section.status_codes == []
    assert [i.code for i in section.scan_result.issues] == [
        IssueCode.UNEXPECTED_COLUMNS
    ]


def test_a_status_heading_nested_in_response_is_read_once(
    parser: DocutilsParser,
) -> None:
    """Two walks reach the same table - the one over Response, which recurses
    into subsections, and the one over the status-code heading itself. Reading
    it twice would list every code of the page twice over."""
    content = (
        ":original_name: demo.html\n\nDemo\n====\n\nURI\n---\n\nPOST /v1/test\n\n"
        "Response\n--------\n\n"
        "Status Codes\n~~~~~~~~~~~~\n\n"
        ".. table:: **Table 2** Status code\n\n"
        "   =========== =============================\n"
        "   Status Code Description\n"
        "   =========== =============================\n"
        "   201         Created.\n"
        "   =========== =============================\n"
    )

    section = _status_codes(parser.parse(content, "demo.rst"))

    assert [c.code for c in section.status_codes] == ["201"]


def test_two_status_tables_on_one_page_both_count(parser: DocutilsParser) -> None:
    """Deduplication is by table, not by code: a page listing its success codes
    in one table and its errors in another documents both."""
    content = (
        ":original_name: demo.html\n\nDemo\n====\n\nURI\n---\n\nPOST /v1/test\n\n"
        "Status Codes\n------------\n\n"
        ".. table:: **Table 2** Normal\n\n"
        "   =========== =============================\n"
        "   Status Code Description\n"
        "   =========== =============================\n"
        "   201         Created.\n"
        "   =========== =============================\n"
        "\n"
        ".. table:: **Table 3** Errors\n\n"
        "   =========== =============================\n"
        "   Status Code Description\n"
        "   =========== =============================\n"
        "   400         Bad request.\n"
        "   =========== =============================\n"
    )

    section = _status_codes(parser.parse(content, "demo.rst"))

    assert [c.code for c in section.status_codes] == ["201", "400"]
