import re

from docutils import nodes
from docutils.core import publish_doctree

from tools.domain.interfaces.parser import RstParser
from tools.domain.ir.endpoint import Endpoint
from tools.domain.ir.enums import URI_RE, HttpMethod

# Matches an API version segment like /v3/, /v2.0/, /api/v1/.
# Captured verbatim so callers see "v3", "v2.0" exactly as they appear.
_VERSION_RE = re.compile(r"/(v\d+(?:\.\d+)?)(?:/|$)", re.IGNORECASE)


class DocutilsParser(RstParser):
    def parse_endpoint(self, content: str, path: str) -> Endpoint:
        # report_level=5 silences docutils warnings on imperfect RST
        doctree = publish_doctree(content, settings_overrides={"report_level": 5})

        match = URI_RE.search(content)
        if not match:
            raise ValueError(f"No HTTP method/URI found in {path}")

        method = HttpMethod(match.group(1).upper())
        uri_path = match.group(2)

        title = self._extract_title(doctree)
        api_version = self._extract_api_version(uri_path, path)

        # `description` and parameter sections will be populated in phase 2 (#5).
        # The source file path is already tracked in DocumentScanResult.document.
        return Endpoint(
            title=title,
            method=method,
            path=uri_path,
            api_version=api_version or "",
        )

    @staticmethod
    def _extract_title(doctree: nodes.document) -> str:
        for section in doctree.traverse(nodes.section):
            title_node = section.next_node(nodes.title)
            if title_node:
                return title_node.astext()
        return ""

    @staticmethod
    def _extract_api_version(uri: str, source_path: str) -> str | None:
        """Best-effort version extraction.

        Looks for a `vN` or `vN.M` segment in the URI first (most reliable),
        then in the source file path. Returns ``None`` if neither yields a match.
        """
        match = _VERSION_RE.search(uri)
        if match:
            return match.group(1)
        # Prefix with "/" so the regex (anchored on `/`) can match a leading segment.
        match = _VERSION_RE.search("/" + source_path)
        if match:
            return match.group(1)
        return None

    def _parse_table(self, doctree: nodes.document, section_name: str):
        """Placeholder for parameter table extraction (phase 2)."""
        return []
