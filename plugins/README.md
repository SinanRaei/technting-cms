# Technting CMS plugins

Each folder is a plugin: `plugin.json` (name, label, version, description, settings) and `plugin.py` with
`register(api)`. Administrators enable and configure installed plugins in the dashboard (Plugins); installing a
plugin means copying its folder here and deploying. See `cms/plugins.py` for the hooks.

`backup-pro` (Technting Backup) keeps its settings on Settings → Backups because they include secrets; see
`cms/offsite.py` and the Arabic setup guide `backup-pro/GUIDE-ar.md`.
