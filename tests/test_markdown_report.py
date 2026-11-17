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


def test_header_names_repo_commit_and_uncommitted_changes() -> None:
    report = render_markdown([], repo="vpc", commit="abc123", dirty=True)

    assert report.startswith("# API reference scan: vpc\n")
    assert "Commit: `abc123`" in report
    assert "changes after this commit" in report
    assert "No documentation errors found." in report


def test_clean_working_copy_has_no_changes_line() -> None:
    report = render_markdown([], repo="vpc", commit="abc123", dirty=False)

    assert "changes after this commit" not in report


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
    assert report.count("| Section | Where | Problem |") == 2
    assert "Commit:" not in report


def test_cells_cannot_break_the_table() -> None:
    finding = _finding("x.rst", "row 1", message="Type `a|b`\nis odd.")

    report = render_markdown([finding], repo="vpc", commit=None, dirty=False)

    assert "| body | row 1 | Type `a\\|b` is odd. |" in report
