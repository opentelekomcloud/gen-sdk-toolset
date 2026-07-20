from pydantic import BaseModel


class Example(BaseModel):
    """One extracted request or response example.

    The raw source is preserved alongside a best-effort JSON representation.
    ``parsed`` remains ``None`` when the example is not valid JSON.
    """

    raw: str
    language: str | None = None
    parsed: dict | list | None = None
    label: str | None = None
