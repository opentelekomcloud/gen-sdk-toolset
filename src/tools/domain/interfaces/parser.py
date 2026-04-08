from typing import Protocol

from tools.domain.ir.endpoint import Endpoint


class RstParser(Protocol):
    def parse_endpoint(self, content: str, path: str) -> Endpoint: ...
