"""Tests for the doc-style classifier."""

from tools.scanner.parsers import classify_doc_style
from tools.scanner.parsers.docutils.style import DocStyle


def test_cce_is_style_a(cce_doc: str) -> None:
    assert classify_doc_style(cce_doc) is DocStyle.STYLE_A


def test_vpc_is_style_a(vpc_doc: str) -> None:
    assert classify_doc_style(vpc_doc) is DocStyle.STYLE_A


def test_kms_is_style_a(kms_doc: str) -> None:
    assert classify_doc_style(kms_doc) is DocStyle.STYLE_A


def test_iam_is_style_a(iam_doc: str) -> None:
    assert classify_doc_style(iam_doc) is DocStyle.STYLE_A


def test_obs_is_s3_compatible(obs_doc: str) -> None:
    assert classify_doc_style(obs_doc) is DocStyle.S3_COMPATIBLE


def test_empty_not_endpoint() -> None:
    assert classify_doc_style("") is DocStyle.NOT_ENDPOINT


def test_intro_not_endpoint() -> None:
    content = """
API Overview
============

This document describes the API.

Concepts
--------

Some concepts here.
"""
    assert classify_doc_style(content) is DocStyle.NOT_ENDPOINT


def test_single_s3_marker_insufficient() -> None:
    """A single keyword in body text shouldn't trip s3 detection."""
    content = """
Some Endpoint
=============

URI
---

GET /v3/foo

Request Parameters
------------------

Note: the Request Syntax for this API is JSON.
"""
    # Only one Style-B heading marker → still style_a.
    assert classify_doc_style(content) is DocStyle.STYLE_A
