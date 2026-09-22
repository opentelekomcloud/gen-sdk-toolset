#!/bin/sh
# Writes /config.js from the container environment so one built image can
# serve any deployment. Runs from the image's CMD, before nginx starts, and
# writes to /tmp - the one place an unprivileged container can always write -
# from where nginx serves it (docker/nginx.conf).
#
# An unset variable becomes an empty string, and the panel then says that
# sign-in is not configured rather than offering a button that cannot work.
set -eu

js_string() {
    # A JS string literal body: backslashes and double quotes escaped.
    printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g'
}

mkdir -p /tmp/panel
cat > /tmp/panel/config.js <<CONFIG
window.__PANEL_CONFIG__ = {
  issuer: "$(js_string "${ZITADEL_ISSUER:-}")",
  clientId: "$(js_string "${ZITADEL_CLIENT_ID:-}")",
  scope: "$(js_string "${ZITADEL_SCOPE:-}")"
};
CONFIG
