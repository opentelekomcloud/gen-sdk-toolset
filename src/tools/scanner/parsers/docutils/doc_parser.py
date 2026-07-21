"""Parse Style-A RST documents into canonical endpoints."""

from __future__ import annotations

from collections.abc import Mapping

from tools.scanner.interfaces import RstParser
from tools.shared.exceptions import ParseFailure
from tools.shared.ir import Endpoint, HttpMethod
from tools.shared.scan import DocumentScanResult, IssueCode

from .context import (
    RepositoryParseContext,
    build_repository_context,
    parse_doctree,
)
from .patterns import API_VERSION_RE, URI_RE
from .routing import extract_sections
from .title import extract_document_title


class DocutilsParser(RstParser):
    def build_repository_context(
        self, documents: Mapping[str, str]
    ) -> RepositoryParseContext:
        return build_repository_context(documents)

    def parse(
        self,
        content: str,
        path: str,
        *,
        context: RepositoryParseContext | None = None,
    ) -> Endpoint:
        doctree = context.doctrees.get(path) if context is not None else None
        if doctree is None:
            doctree = parse_doctree(content)

        method, uri = self._extract_method_and_uri(content, path)
        return Endpoint(
            path=path,
            title=extract_document_title(content),
            method=method,
            uri=uri,
            api_version=self._extract_api_version(uri, path),
            sections=extract_sections(doctree, method, uri, context=context),
            scan_result=DocumentScanResult(),
        )

    @staticmethod
    def _extract_method_and_uri(content: str, path: str) -> tuple[HttpMethod, str]:
        match = URI_RE.search(content)
        if not match:
            raise ParseFailure(
                IssueCode.NO_URI_MATCH,
                details=f"No 'METHOD /path' line found in {path}",
            )
        return HttpMethod(match.group(1).upper()), match.group(2)

    @staticmethod
    def _extract_api_version(uri: str, source_path: str) -> str | None:
        """Read an API version from the URI, then fall back to the source path."""
        match = API_VERSION_RE.search(uri)
        if match:
            return match.group(1).lower()
        match = API_VERSION_RE.search("/" + source_path)
        if match:
            return match.group(1).lower()
        return None
