# Security policy

## Reporting a vulnerability

Please do not post a security problem in public. Report it privately by e-mail to **reach@technting.com**, with
"Security" in the subject. Only the Technting team reads it.

Include what you can:

- the version (Settings, Updates in the dashboard, or `technting_cms/__init__.py`),
- how the site is installed (Docker, `install.sh` or manual) and which database it uses,
- the steps to reproduce, and what an attacker could do with it.

We aim to answer within 5 working days and to ship a fix for a confirmed problem as soon as it is ready. We will tell
you when the fix is released and, if you like, credit you in `CHANGELOG.md`.

## Supported versions

Security fixes go into the latest release. Please upgrade before you report, in case the problem is already fixed.

## Scope

In scope: the code in this repository, including Technting CRM, Technting Forms, Technting Shield for CMS and every
plugin in `plugins/`.

Out of scope: the public demo at cms.technting.com (it is reset every 2 hours and open to everyone by design),
denial of service by sheer traffic, and problems in your own server, proxy or hosting setup.
