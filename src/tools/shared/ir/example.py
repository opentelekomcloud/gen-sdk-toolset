from pydantic import BaseModel, ConfigDict


class Example(BaseModel):
    """One extracted request or response example.

    The raw source is preserved alongside a best-effort JSON representation.
    ``parsed`` remains ``None`` when the example is not valid JSON.
    """

    model_config = ConfigDict(extra="forbid")

    raw: str
    language: str | None = None
    parsed: dict | list | None = None
    label: str | None = None
