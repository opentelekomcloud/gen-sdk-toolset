#!/bin/sh
# Writes /config.js from the container environment so one built image can
# serve any deployment. Runs before nginx starts (see Dockerfile.frontend).
#
# An unset variable becomes an empty string, and the panel then says that
# sign-in is not configured rather than offering a button that cannot work.
set -eu

js_string() {
    # A JS string literal body: backslashes and double quotes escaped.
    printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g'
}

cat > /usr/share/nginx/html/config.js <<CONFIG
window.__PANEL_CONFIG__ = {
  issuer: "$(js_string "${ZITADEL_ISSUER:-}")",
  clientId: "$(js_string "${ZITADEL_CLIENT_ID:-}")",
  scope: "$(js_string "${ZITADEL_SCOPE:-}")"
};
CONFIG
