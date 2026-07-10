from pydantic import BaseModel, Field

from .endpoint import Endpoint


class Service(BaseModel):
    """A logical group of endpoints belonging to one OTC service.

    Pure IR — describes the *API*, not the scanner's progress. Scan-time
    statistics live on :class:`tools.shared.report.RepoScanResult`.
    """

    service_name: str
    endpoints: list[Endpoint] = Field(default_factory=list)
