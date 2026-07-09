"""Text-recognition regexes for OTC RST docs."""

from __future__ import annotations

import re

from tools.shared.ir import HttpMethod

# Single source of the method alternation, derived from the domain enum.
HTTP_METHODS_RE = "|".join(m.value for m in HttpMethod)

# A URI line in a doc's "URI" section. Two forms occur in OTC docs:
#   POST /v3/{project_id}/configurations
#   POST https://{Endpoint}/v3/{project_id}/configurations   (host form)
URI_RE = re.compile(
    rf"^\s*({HTTP_METHODS_RE})\s+(?:https?://[^/\s]+)?(/\S+)\s*$",
    re.IGNORECASE | re.MULTILINE,
)

# Leading HTTP-wire-format request line inside an example block, e.g.
# "POST https://{Endpoint}/v3/..." followed by a JSON body. Stripped so a
# best-effort JSON parse has a chance on what follows.
HTTP_PREFIX_RE = re.compile(
    rf"^\s*({HTTP_METHODS_RE})\s+https?://\S+\s*\n",
    re.IGNORECASE,
)
