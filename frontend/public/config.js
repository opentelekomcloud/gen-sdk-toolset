/* Runtime configuration of the panel. Deliberately empty in the repository: the
   dev server falls back to the VITE_* variables in .env, and the container
   image overwrites this file from its environment at start
   (frontend/docker/10-panel-config.sh). */
window.__PANEL_CONFIG__ = {};
