#!/usr/bin/env bash
# Connect Technting CMS enquiry emails to Gmail SMTP (enquiries are always saved in the dashboard inbox;
# this adds an email copy to the team mailbox).
# Run on the server:  sudo bash /home/technting/technting-cms/deploy/setup_gmail_smtp.sh
# Asks for the Gmail address and a Gmail app password (hidden), tests the login, writes the
# TECHNTING_CMS_SMTP_* lines into /home/technting/technting-cms/.env (mode 600) and restarts Technting CMS.
set -euo pipefail

ENV=/home/technting/technting-cms/.env
if [ "$(id -u)" -ne 0 ]; then echo "Please run with sudo." >&2; exit 1; fi
if [ ! -f "$ENV" ]; then echo "Technting CMS is not installed ($ENV missing)." >&2; exit 1; fi

read -rp "Gmail address that will send the enquiry emails: " GUSER
case "$GUSER" in *@*.*) ;; *) echo "That does not look like an email address." >&2; exit 1 ;; esac
read -rsp "Gmail app password (16 letters; typing is hidden): " GPASS
echo
GPASS="${GPASS// /}"
if [ "${#GPASS}" -lt 16 ]; then
  echo "An app password has 16 letters. Create one at https://myaccount.google.com/apppasswords" >&2
  exit 1
fi

echo "Testing the login with smtp.gmail.com:465 ..."
if ! GUSER="$GUSER" GPASS="$GPASS" python3 - <<'PY'
import os, smtplib, ssl, sys
try:
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15, context=ssl.create_default_context()) as s:
        s.login(os.environ["GUSER"], os.environ["GPASS"])
except smtplib.SMTPAuthenticationError:
    print("Gmail rejected the login. Check the address and the app password (2-Step Verification must be on).", file=sys.stderr)
    sys.exit(1)
except Exception as exc:
    print(f"Could not reach Gmail: {type(exc).__name__}", file=sys.stderr)
    sys.exit(1)
print("Login OK.")
PY
then echo "Nothing was changed." >&2; exit 1; fi

TMP=$(mktemp)
grep -v '^TECHNTING_CMS_SMTP_' "$ENV" > "$TMP" || true
cat >> "$TMP" <<EOF
TECHNTING_CMS_SMTP_HOST=smtp.gmail.com
TECHNTING_CMS_SMTP_PORT=465
TECHNTING_CMS_SMTP_SECURITY=ssl
TECHNTING_CMS_SMTP_USERNAME=$GUSER
TECHNTING_CMS_SMTP_PASSWORD=$GPASS
EOF
install -m 600 -o technting -g technting "$TMP" "$ENV"
rm -f "$TMP"
unset GPASS
systemctl restart technting-cms
echo "Done. New enquiries are saved in the inbox and emailed to the team mailbox."
