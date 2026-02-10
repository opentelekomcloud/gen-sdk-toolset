from typing import Protocol
from gen_sdk_tooling.domain.ir.endpoint import Endpoint


class RstParser(Protocol):
    """Порт для преобразования RST в структурированные модели."""

    def parse_endpoint(self, content: str, path: str) -> Endpoint:
        """Извлекает данные из RST и заполняет модель Endpoint."""
        ...
