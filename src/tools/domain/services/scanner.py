import logging

from tools.domain.interfaces.doc_provider import DocProvider
from tools.domain.interfaces.parser import RstParser
from tools.domain.ir import URI_RE, Service

logger = logging.getLogger(__name__)


class ScannerService:
    def __init__(self, doc_provider: DocProvider, parser: RstParser):
        self.doc_provider = doc_provider
        self.parser = parser

    def find_endpoints(self, repo: str, branch: str) -> Service:
        logger.info("Starting scan for repo: %s (branch: %s)", repo, branch)  #
        endpoints = []
        paths = self.doc_provider.list_files(repo, branch)
        logger.debug("Found %d total files in repository", len(paths))  #
        for path in paths:
            content = self.doc_provider.fetch_content(repo, path)
            if self._is_api_endpoint(content):
                logger.info("Processing endpoint: %s", path)  #
                endpoint = self.parser.parse_endpoint(content, path)
                endpoints.append(endpoint)
        return Service(service_name=repo, endpoints=endpoints)

    @staticmethod
    def _is_api_endpoint(content: str) -> bool:
        return bool(URI_RE.search(content))
