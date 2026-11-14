"""Technting Backup: encrypted offsite copies of the nightly backups. The work is in cms/offsite.py; settings and
status are on Settings → Backups (secrets never go through the generic plugin settings form)."""


def register(api):
    from cms import offsite

    def scheduled(log=None, **_):
        offsite.tick(log=log)

    def backup_failed(**_):
        offsite.check_alerts()

    api.add_action("scheduled", scheduled)
    api.add_action("backup_failed", backup_failed)
