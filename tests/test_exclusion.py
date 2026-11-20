"""The rules that put a source path outside production coverage.

Whole real pages are exercised through the scanner in test_scanner.py. These
tests pin the edges of each rule with the smallest page that shows one.
"""

from __future__ import annotations

import pytest

from tools.scanner.exclusion import page_exclusion, path_exclusion
from tools.shared.scan import (
    ExcludedDocument,
    ExclusionEvidence,
    ExclusionReason,
    ReviewCandidate,
)

SEGMENTS = {"calling_apis": ExclusionReason.guide}
SAMPLES = frozenset({"org/sandbox"})


def _by_path(path: str, repo: str = "org/svc") -> ExcludedDocument | None:
    return path_exclusion(repo, path, segments=SEGMENTS, sample_repositories=SAMPLES)


def _page(body: str, title: str = "Querying Disks") -> str:
    return f"{title}\n{'=' * len(title)}\n\n{body}\n"


# --- by path --- #


@pytest.mark.parametrize(
    ("directory", "label"),
    [
        ("apis_discarded", "Discarded"),
        ("api_v1_to_be_discarded", "To Be Discarded"),
        ("deprecated_apis", "Deprecated"),
        ("outdated_apis_v1", "Outdated"),
        ("historical_apis", "Historical APIs"),
        ("data_management_old_version", "Old Version"),
        ("apis_unavailable_soon", "Unavailable Soon"),
        ("apis_to_be_taken_offline", "To Be Taken Offline"),
        ("job_object_apis_v1_not_recommended", "Not Recommended"),
    ],
)
def test_a_directory_named_with_a_lifecycle_label_retires_its_pages(
    directory: str, label: str
) -> None:
    entry = _by_path(f"api-ref/source/{directory}/page.rst")

    assert entry == ExcludedDocument(
        path=f"api-ref/source/{directory}/page.rst",
        reason=ExclusionReason.retired,
        evidence=ExclusionEvidence(source=f"api-ref/source/{directory}", text=label),
    )


@pytest.mark.parametrize(
    "path",
    [
        "api-ref/source/apis_recommended/page.rst",
        "api-ref/source/api_reference_classic_vpn/page.rst",
        "api-ref/source/obtaining_an_api_version/page.rst",
        # A file name is an operation, and "Not Recommended" retires only a
        # section; the page's own content decides about the operation.
        "api-ref/source/apis/querying_jobs_not_recommended.rst",
        "api-ref/source/apis/querying_deprecated_flavors.rst",
    ],
)
def test_a_path_without_a_section_label_is_kept(path: str) -> None:
    assert _by_path(path) is None


def test_the_outermost_deciding_directory_is_the_evidence() -> None:
    entry = _by_path("api-ref/source/historical_apis/data_management_old_version/x.rst")

    assert entry is not None
    assert entry.evidence == ExclusionEvidence(
        source="api-ref/source/historical_apis", text="Historical APIs"
    )


def test_a_sample_repository_wins_over_a_configured_segment() -> None:
    entry = _by_path("api-ref/source/calling_apis/x.rst", repo="org/sandbox")

    assert entry is not None
    assert entry.reason is ExclusionReason.sample


# --- by content --- #


@pytest.mark.parametrize(
    "notice",
    [
        "This API has been deprecated. Use another API.",
        "This API is deprecated.",
        "This API will be discarded.",
        "This interface is to be taken offline.",
        "This API will be unavailable soon.",
        "This API will be unavailable.",
        "This API is unavailable soon.",
        "This API is no longer available.",
        "This API is no longer supported.",
        "This API is retained only for compatibility.",
        "This API is for compatibility only.",
        # EVS, Expanding the Capacity of an EVS Disk, under apis_recommended.
        "This API call exists for compatibility reasons only and is not meant "
        "to be used.",
        "This API is not meant to be used.",
    ],
)
def test_an_operation_wide_notice_retires_the_page(notice: str) -> None:
    content = _page(f".. important::\n\n   {notice}")

    entry = page_exclusion("p.rst", content)

    assert entry == ExcludedDocument(
        path="p.rst",
        reason=ExclusionReason.retired,
        evidence=ExclusionEvidence(source="p.rst", line=6, text=notice),
    )


def test_a_lifecycle_label_in_the_title_retires_the_page() -> None:
    title = "Creating a Connection (to Be Taken Offline)"

    entry = page_exclusion("p.rst", _page("This API creates a connection.", title))

    assert entry == ExcludedDocument(
        path="p.rst",
        reason=ExclusionReason.retired,
        evidence=ExclusionEvidence(source="p.rst", line=1, text=title),
    )


@pytest.mark.parametrize(
    "title",
    [
        "Querying API Versions (Compatible with OpenStack)",
        "Querying Disks (Recommended)",
        # "Not Recommended" retires a section, not the operation named by it.
        "Querying Jobs (Not Recommended)",
    ],
)
def test_a_title_without_a_lifecycle_label_keeps_the_page(title: str) -> None:
    assert page_exclusion("p.rst", _page("This API queries things.", title)) is None


def test_an_unclear_notice_keeps_the_page_as_a_review_candidate() -> None:
    """The word is there, but not about the operation: a person decides."""
    line = "The v1 response format is deprecated; use the v2 fields."

    entry = page_exclusion("p.rst", _page(line))

    assert entry == ReviewCandidate(
        path="p.rst",
        evidence=ExclusionEvidence(source="p.rst", line=4, text=line),
    )


def test_an_operation_unavailable_somewhere_is_kept_for_review() -> None:
    """ "Unavailable" in the present limits an operation - to a region, a
    state - rather than withdrawing it, so it must not drop out of coverage."""
    line = "This API is unavailable in the eu-nl region."

    entry = page_exclusion("p.rst", _page(line))

    assert entry == ReviewCandidate(
        path="p.rst",
        evidence=ExclusionEvidence(source="p.rst", line=4, text=line),
    )


def test_a_title_opening_with_a_substitution_is_still_found() -> None:
    title = "|br| Creating a Cluster (Deprecated)"

    entry = page_exclusion("p.rst", _page("This API creates a cluster.", title))

    assert entry == ExcludedDocument(
        path="p.rst",
        reason=ExclusionReason.retired,
        evidence=ExclusionEvidence(source="p.rst", line=1, text=title),
    )


def test_a_link_to_a_retired_page_says_nothing_about_this_one() -> None:
    """An index lists its children by title; one of them being discarded does
    not make the index, or any page linking to it, a candidate."""
    body = "-  :ref:`Creating a Cluster (Discarded) <createcluster>`"

    assert page_exclusion("index.rst", _page(body, "Cluster Management")) is None


def test_a_field_notice_inside_a_table_is_not_read() -> None:
    table = (
        "+-------+------------------------------------------+\n"
        "| Name  | Description                              |\n"
        "+=======+==========================================+\n"
        "| token | This parameter is to be discarded.       |\n"
        "+-------+------------------------------------------+"
    )

    assert page_exclusion("p.rst", _page(table)) is None


@pytest.mark.parametrize(
    "body",
    ["| This API will be discarded.", "+ This API will be discarded."],
    ids=["line-block", "plus-bullet"],
)
def test_a_line_block_or_plus_bullet_is_read_as_prose(body: str) -> None:
    """Only a grid table's rows and borders are skipped: a line that merely
    starts with "|" or "+" is still text a reader sees."""
    entry = page_exclusion("p.rst", _page(body))

    assert entry is not None
    assert entry.evidence == ExclusionEvidence(source="p.rst", line=4, text=body)


def test_a_literal_block_is_not_read() -> None:
    body = (
        "Example response:\n\n"
        ".. code-block::\n\n"
        '   {"note": "This API has been deprecated."}\n\n'
        "This API queries disks."
    )

    assert page_exclusion("p.rst", _page(body)) is None


def test_a_page_without_lifecycle_words_is_kept() -> None:
    content = _page(".. note::\n\n   The API in Querying Projects is recommended.")

    assert page_exclusion("p.rst", content) is None
