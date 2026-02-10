from docutils.core import publish_doctree
from docutils import nodes

from gen_sdk_tooling.domain.interfaces.parser import RstParser
from gen_sdk_tooling.domain.ir.endpoint import Endpoint
from gen_sdk_tooling.domain.ir.enums import HttpMethod, URI_RE


class DocutilsParser(RstParser):
    def parse_endpoint(self, content: str, path: str) -> Endpoint:
        doctree = publish_doctree(
            content,
            settings_overrides={'report_level': 5}
        )

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
            title=title,
            method=method,
            path=uri_path,
            description=f"Source: {path}"
        )

        # 4. В будущем здесь будет вызов приватных методов для парсинга таблиц:
        # endpoint.path_parameters = self._parse_table(doctree, "Path Parameters")
        # endpoint.request_body = self._parse_table(doctree, "Request Parameters")

        return endpoint

    def _parse_table(self, doctree: nodes.document, section_name: str):
        pass
