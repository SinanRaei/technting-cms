# Contributing to Technting CMS

Thank you for helping. Bug reports, translations, themes, plugins and code are all welcome.

## Reporting a bug

Open an issue at <https://github.com/SinanRaei/technting-cms/issues>, or e-mail reach@technting.com, with the version, how you installed it (Docker, `install.sh` or manual), the database, what you did,
what you expected and what happened. For a security problem, follow [SECURITY.md](SECURITY.md) instead.

## Setting up

See "For developers" in [README.md](README.md). In short:

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
export TECHNTING_CMS_DEBUG=1 TECHNTING_CMS_VAR_DIR=./var
python manage.py migrate
python manage.py test
```

## Changes and patches

Send a change as a pull request at <https://github.com/SinanRaei/technting-cms/pulls>, or as a patch
(`git format-patch`) by e-mail to reach@technting.com. Contributions are accepted under the GPL-3.0, the licence of the
project.

- Keep one change per patch, and explain why it is needed.
- Run `python manage.py test` before you send it, and add a test for a bug fix or a new feature.
- The dashboard is bilingual. Every new interface string needs its Arabic translation (`cms/ui_i18n.py`, or the
  `ui_ar.py` file of the app or plugin), and layouts must work right to left.
- A new plugin goes in its own folder in `plugins/` with a `plugin.json` and a `plugin.py`; look at an existing plugin
  first.
- Do not add tracking, analytics or calls to outside services that are on by default.

## Licence

Technting CMS is licensed under the GNU General Public License, version 3. By sending a contribution you agree that it
is released under the same licence. The Technting name and logo are not part of that licence.
