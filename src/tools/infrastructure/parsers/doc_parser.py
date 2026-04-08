from docutils import nodes
from docutils.core import publish_doctree

from tools.domain.interfaces.parser import RstParser
from tools.domain.ir.endpoint import Endpoint
from tools.domain.ir.enums import URI_RE, HttpMethod


class DocutilsParser(RstParser):
    def parse_endpoint(self, content: str, path: str) -> Endpoint:
        doctree = publish_doctree(content, settings_overrides={"report_level": 5})

        match = URI_RE.search(content)
        method = HttpMethod(match.group(1).upper()) if match else HttpMethod.GET
        uri_path = match.group(2) if match else "unknown"

        title = ""
        for section in doctree.traverse(nodes.section):
            title_node = section.next_node(nodes.title)
            if title_node:
                title = title_node.astext()
                break

        endpoint = Endpoint(
            title=title, method=method, path=uri_path, description=f"Source: {path}"
        )
        # endpoint.path_parameters = self._parse_table(doctree, "Path Parameters")
        # endpoint.request_body = self._parse_table(doctree, "Request Parameters")

        return endpoint

    def _parse_table(self, doctree: nodes.document, section_name: str):
        pass
