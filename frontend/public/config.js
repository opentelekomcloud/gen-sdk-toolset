/* Runtime configuration of the panel. Deliberately empty in the repository: the
   dev server falls back to the VITE_* variables in .env, and the container
   image serves /config.js generated from its environment at start instead
   (frontend/docker/panel-config.sh). */
window.__PANEL_CONFIG__ = {};
