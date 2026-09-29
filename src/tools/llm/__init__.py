"""LLM client: one chat-completion request in, one ``Result`` out, failures as data."""

from .factory import build_llm_service
from .port import FAILURES, LLM, Request, Result

__all__ = ["FAILURES", "LLM", "Request", "Result", "build_llm_service"]
