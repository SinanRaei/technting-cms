"""Load researched companies into the prospect list from an Excel, CSV or JSON file (see crm.prospect_io).

    manage.py crm_import_prospects leads.xlsx [--dry-run] [--add-only | --unverified-only] [--notes]

A company already in the list gets its research fields refreshed; its owner, deal and notes typed in the dashboard are
kept. Rows may carry unverified entries; those are added to what the company already has, never replacing it.
With --unverified-only, only those entries are merged into existing companies. Nothing is ever moved to the leads."""
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from crm.prospect_io import ProspectFileError, apply_rows, read_rows


class Command(BaseCommand):
    help = "Import researched companies into the CRM prospect list (never into the leads)."

    def add_arguments(self, parser):
        parser.add_argument("path")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--notes", action="store_true", help="also fill the notes field from the file when it is empty")
        parser.add_argument("--unverified-only", action="store_true", help="only add the rows' unverified entries to existing companies")
        parser.add_argument("--add-only", action="store_true", help="only add companies that are not in the list yet")

    def handle(self, path, dry_run=False, notes=False, unverified_only=False, add_only=False, **kw):
        try:
            rows = read_rows(Path(path).read_bytes(), path)
        except (OSError, ProspectFileError) as e:
            raise CommandError(f"cannot read {path}: {e}")
        mode = "unverified" if unverified_only else "add" if add_only else "update"
        res = apply_rows(rows, mode=mode, dry_run=dry_run, fill_notes=notes)
        self.stdout.write(f"{'[dry run] ' if dry_run else ''}{res.line()}")
        for n, why in res.errors[:20]:
            self.stdout.write(f"  row {n}: {why}")
