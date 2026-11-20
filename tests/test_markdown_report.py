"""The markdown report a documentation author reads."""

from __future__ import annotations

from tools.scanner.doc_checks import DocCheck, DocFinding, render_markdown


def _finding(path: str, location: str, message: str = "Broken.") -> DocFinding:
    return DocFinding(
        check=DocCheck.TYPE_PROSE,
        path=path,
        section="body",
        location=location,
        message=message,
    )


# --------------------------------------------------------------------------- #
# Header
# --------------------------------------------------------------------------- #
def test_header_names_repo_commit_and_uncommitted_changes() -> None:
    report = render_markdown([], repo="vpc", commit="abc123", dirty=True)

    assert report.startswith("# API reference scan: vpc\n")
    assert "Commit: `abc123`" in report
    assert "changes after this commit" in report
    assert "No documentation errors found." in report


def test_clean_working_copy_has_no_changes_line() -> None:
    report = render_markdown([], repo="vpc", commit="abc123", dirty=False)

    assert "changes after this commit" not in report


# --------------------------------------------------------------------------- #
# Tables
# --------------------------------------------------------------------------- #
def test_one_table_per_file_in_the_given_order() -> None:
    findings = [
        _finding("api-ref/source/a.rst", "row 1"),
        _finding("api-ref/source/a.rst", "row 2"),
        _finding("api-ref/source/b.rst", "row 1"),
    ]

    report = render_markdown(findings, repo="vpc", commit=None, dirty=False)

    assert "**3 documentation error(s) in 2 file(s).**" in report
    assert report.index("## api-ref/source/a.rst") < report.index(
        "## api-ref/source/b.rst"
    )
    assert report.count("| Line | Section | Where | Problem |") == 2
    assert "Commit:" not in report


def test_cells_cannot_break_the_table() -> None:
    finding = _finding("x.rst", "row 1", message="Type `a|b`\nis odd.")

    report = render_markdown([finding], repo="vpc", commit=None, dirty=False)

    assert "| body | row 1 | Type `a\\|b` is odd. |" in report


def test_line_column_shows_the_rst_line_or_a_dash() -> None:
    with_line = DocFinding(
        check=DocCheck.TYPE_PROSE,
        path="x.rst",
        section="body",
        location="row 1",
        message="Broken.",
        line=12,
    )
    without_line = _finding("x.rst", "row 2")

    report = render_markdown(
        [with_line, without_line], repo="vpc", commit=None, dirty=False
    )

    assert "| Line | Section | Where | Problem |" in report
    assert "| 12 | body | row 1 | Broken. |" in report
    assert "| — | body | row 2 | Broken. |" in report
