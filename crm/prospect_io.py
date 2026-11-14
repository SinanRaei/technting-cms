"""Prospect list import and export, shared by the dashboard (Import / Export buttons) and manage.py crm_import_prospects.

Files: Excel (.xlsx), CSV or JSON. Headers can be our export headers, the field names, or the headers of the research
workbooks (one company per row), so those files load as they are. An Excel file may carry a second sheet
"Unverified info" (one row per entry); a CSV carries the entries as JSON in one column.

Matching is on country + website domain, or name when there is no website. Import never moves a company to the leads,
never changes a company already moved, and keeps the owner and notes typed in the dashboard."""
import csv
import io
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime

from django.db import transaction

from .models import Prospect
from .services import merge_unverified, web_domain

RESEARCH = ["name", "name_ar", "country", "city", "sector", "sub_sector", "size_band", "ownership", "listed_on", "website",
            "email", "email_source", "email_verified", "phone", "phone_source", "phone_verified", "contact_page", "linkedin",
            "officer", "checked_on", "fit_score", "fit_reason", "fit_source", "services", "priority"]
LIMITS = {f.name: f.max_length for f in Prospect._meta.fields if getattr(f, "max_length", None)}
MAX_ROWS = 5000

# export order and headers; import also accepts these headers
COLUMNS = [("name", "Company"), ("name_ar", "Company (Arabic)"), ("country", "Country"), ("city", "City"), ("sector", "Sector"),
           ("sub_sector", "Sub-sector"), ("size_band", "Size"), ("ownership", "Ownership"), ("listed_on", "Listed on"),
           ("website", "Website"), ("email", "Company email"), ("email_source", "Email source"),
           ("email_verified", "Email seen on company site"), ("phone", "Main phone"), ("phone_source", "Phone source"),
           ("phone_verified", "Phone seen on company site"), ("contact_page", "Contact page"), ("linkedin", "LinkedIn company page"),
           ("officer", "Named officer"), ("checked_on", "Date checked"), ("fit_score", "Fit score"), ("priority", "Priority"),
           ("services", "Suggested services"), ("fit_reason", "Why they fit"), ("fit_source", "Fit source"),
           ("status", "Status"), ("owner", "Owner"), ("notes", "Notes"), ("deal", "Deal (moved to leads)")]
UNV_COLUMNS = [("type", "Type"), ("role", "Role"), ("name", "Name"), ("email", "Email"), ("phone", "Phone"), ("source", "Source"),
               ("source_kind", "Source type"), ("note", "Note"), ("added", "Added")]
_ALIASES = {
    # research workbook headers
    "company (en)": "name", "company (ar)": "name_ar", "size band (public)": "size_band", "company email (as published)": "email",
    "email source url": "email_source", "email verified?": "email_verified", "main phone (as published)": "phone",
    "phone source url": "phone_source", "phone verified?": "phone_verified", "contact page / form": "contact_page",
    "named officer (from company site)": "officer", "fit score (1-5)": "fit_score", "fit source url": "fit_source",
    "suggested first service(s)": "services", "unverified info (json)": "unverified",
}
HEADER_TO_FIELD = {**{h.lower(): f for f, h in COLUMNS}, **{f: f for f, _ in COLUMNS}, **_ALIASES, "unverified": "unverified"}
STATUS_IN = {"open": Prospect.OPEN, "not contacted yet": Prospect.OPEN, "hold": Prospect.HOLD, "on hold": Prospect.HOLD,
             "dnc": Prospect.DO_NOT_CONTACT, "do not contact": Prospect.DO_NOT_CONTACT}
STATUS_OUT = dict(Prospect.STATUS)


class ProspectFileError(ValueError):
    """The file cannot be read at all (wrong type, broken file, too many rows)."""


# ---------------------------------------------------------------- reading files
def _cell(v):
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    s = "" if v is None else str(v).strip()
    if s[:1] == "'" and s[1:2] in ("=", "+", "-", "@"):  # undo the export's formula guard (see _safe)
        s = s[1:]
    return s


def _map_row(raw):
    out = {}
    for k, v in raw.items():
        f = HEADER_TO_FIELD.get(str(k or "").strip().lower())
        if f and f not in out:
            out[f] = v
    return out


def read_rows(data, filename):
    """Bytes of an uploaded file -> list of dicts keyed by field name (values still raw)."""
    name = (filename or "").lower()
    if name.endswith(".json"):
        try:
            rows = json.loads(data.decode("utf-8-sig"))
        except (UnicodeDecodeError, ValueError) as e:
            raise ProspectFileError(f"Not a valid JSON file: {e}")
        if not isinstance(rows, list):
            raise ProspectFileError("The JSON file must hold a list of companies.")
        rows = [_map_row(r) for r in rows if isinstance(r, dict)]
    elif name.endswith(".csv"):
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = data.decode("cp1256", errors="replace")  # Arabic Windows exports
        try:
            dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        rows = [_map_row(r) for r in csv.DictReader(io.StringIO(text), dialect=dialect)]
        for r in rows:
            if isinstance(r.get("unverified"), str) and r["unverified"].strip():
                try:
                    r["unverified"] = [{k: _cell(v) for k, v in e.items()} for e in json.loads(r["unverified"]) if isinstance(e, dict)]
                except (ValueError, AttributeError):
                    r["unverified"] = []
    elif name.endswith(".xlsx"):
        from openpyxl import load_workbook
        try:
            wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        except Exception as e:  # zip or XML errors from a broken file
            raise ProspectFileError(f"Not a valid Excel file: {e}")
        sheet = next((s for s in wb.sheetnames if s.lower() == "unverified info"), None)
        only_unverified = sheet and "Companies" not in wb.sheetnames and len(wb.sheetnames) == 1
        rows = []
        if not only_unverified:
            ws = wb["Companies"] if "Companies" in wb.sheetnames else wb.worksheets[0]
            it = ws.iter_rows(values_only=True)
            head = [_cell(h) for h in next(it, [])]
            rows = [_map_row({h: _cell(v) for h, v in zip(head, r)}) for r in it if any(v not in (None, "") for v in r)]
        if sheet:
            uit = wb[sheet].iter_rows(values_only=True)
            uhead = [_cell(h).lower() for h in next(uit, [])]
            ukeys = ({h.lower(): f for f, h in UNV_COLUMNS} | {f: f for f, _ in UNV_COLUMNS}
                     | {"email (as published)": "email", "phone (as published)": "phone", "source url": "source", "found on": "added"})
            by_company = {}
            for r in uit:
                d = {uhead[i]: _cell(v) for i, v in enumerate(r) if i < len(uhead)}
                key = (d.get("country", ""), d.get("company", "").lower())
                e = {ukeys[h]: v for h, v in d.items() if h in ukeys}
                if key[1] and e:
                    e["type"] = "person" if e.get("type", "").lower().startswith("person") else "company"
                    by_company.setdefault(key, []).append(e)
            if only_unverified:  # the "unverified contacts" workbook: one sheet, entries only
                names = {}
                for r in wb[sheet].iter_rows(min_row=2, values_only=True):
                    if len(r) > 1 and r[1]:
                        names.setdefault((_cell(r[0]), _cell(r[1]).lower()), _cell(r[1]))
                rows = [{"country": k[0], "name": names.get(k, k[1]), "unverified": v} for k, v in by_company.items()]
            for r in rows:
                if only_unverified:
                    continue
                extra = by_company.get((_cell(r.get("country")), _cell(r.get("name")).lower()))
                if extra:
                    r["unverified"] = list(r.get("unverified") or []) + extra
        wb.close()
    else:
        raise ProspectFileError("Use an Excel (.xlsx), CSV or JSON file.")
    if len(rows) > MAX_ROWS:
        raise ProspectFileError(f"The file has {len(rows)} rows; the limit is {MAX_ROWS}. Split it into smaller files.")
    return rows


# ---------------------------------------------------------------- cleaning one row
def _bool(v):
    return v is True or _cell(v).lower() in {"yes", "true", "1", "y", "نعم"}


def clean(row):
    """Raw row -> Prospect research fields. Raises ValueError with a short reason when the row cannot be used."""
    out = {}
    for k in RESEARCH:
        v = row.get(k)
        if k in ("email_verified", "phone_verified"):
            out[k] = _bool(v)
        elif k == "fit_score":
            try:
                out[k] = max(1, min(5, int(float(_cell(v) or 3))))
            except ValueError:
                out[k] = 3
        elif k == "services":
            text = " ".join(v) if isinstance(v, list) else _cell(v)
            out[k] = list(dict.fromkeys(re.findall(r"\b[A-Z]{1,3}\d{1,2}\b", text.upper())))[:12]
        elif k == "priority":
            p = _cell(v).upper()[:1]
            out[k] = p if p in ("A", "B", "C") else "B"
        elif k == "checked_on":
            s = _cell(v)[:10]
            try:
                out[k] = date.fromisoformat(s) if s else None
            except ValueError:
                out[k] = None
        else:
            out[k] = _cell(v)[:LIMITS.get(k, 100000)]
    if not out["name"]:
        raise ValueError("no company name")
    if not (out["website"] or out["contact_page"]):
        raise ValueError("no website or contact page")
    if out["email"] and "@" not in out["email"]:
        out["email"] = ""
    out["domain"] = web_domain(out["website"])
    return out


def _find(country, domain, name):
    qs = Prospect.objects.filter(country=country)
    return (qs.filter(domain=domain).first() if domain else None) or qs.filter(name__iexact=name).first()


# ---------------------------------------------------------------- applying rows
@dataclass
class Result:
    added: int = 0
    updated: int = 0
    skipped: int = 0
    entries: int = 0
    errors: list = field(default_factory=list)          # [(row number, reason)]
    added_names: list = field(default_factory=list)
    updated_names: list = field(default_factory=list)

    def line(self):
        return f"added {self.added}, updated {self.updated}, skipped {self.skipped}, unverified entries added {self.entries}"


def apply_rows(rows, mode="update", dry_run=False, fill_notes=False):
    """mode: "update" (add new, refresh existing), "add" (only new companies), "unverified" (only merge unverified entries).
    Row numbers in errors count the header as row 1, as a spreadsheet shows them."""
    res = Result()
    with transaction.atomic():
        for n, row in enumerate(rows, 2):
            if mode == "unverified":
                p = _find(_cell(row.get("country")), web_domain(_cell(row.get("website"))), _cell(row.get("name")))
                k = merge_unverified(p, row.get("unverified")) if p else 0
                if k:
                    p.save(update_fields=["unverified", "updated_at"])
                    res.entries += k
                    res.updated += 1
                    res.updated_names.append(p.name)
                else:
                    res.skipped += 1
                continue
            try:
                data = clean(row)
            except ValueError as e:
                res.skipped += 1
                res.errors.append((n, str(e)))
                continue
            p = _find(data["country"], data["domain"], data["name"])
            status = STATUS_IN.get(_cell(row.get("status")).lower())
            if p is None:
                p = Prospect(**data, notes=_cell(row.get("notes"))[:5000], status=status or Prospect.OPEN)
                res.added += 1
                res.added_names.append(data["name"])
            elif mode == "add":
                res.skipped += 1
                continue
            else:
                for k, v in data.items():
                    setattr(p, k, v)
                if status and p.status != Prospect.MOVED:  # never undo a move to the leads
                    p.status = status
                if fill_notes and not p.notes:
                    p.notes = _cell(row.get("notes"))[:5000]
                res.updated += 1
                res.updated_names.append(p.name)
            res.entries += merge_unverified(p, row.get("unverified"))
            p.save()
        if dry_run:
            transaction.set_rollback(True)
    return res


# ---------------------------------------------------------------- export
def _safe(v):
    """Stop spreadsheet formulas in researched text (a cell starting with = + - @ runs as a formula when opened)."""
    s = "" if v is None else str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


def _value(p, f):
    if f == "services":
        return ", ".join(p.services or [])
    if f in ("email_verified", "phone_verified"):
        return "Yes" if getattr(p, f) else "No"
    if f == "checked_on":
        return p.checked_on.isoformat() if p.checked_on else ""
    if f == "status":
        return STATUS_OUT.get(p.status, p.status)
    if f == "owner":
        return p.owner.get_username() if p.owner else ""
    if f == "deal":
        return p.deal.title if p.deal_id and p.deal else ""
    return getattr(p, f)


def export_csv(qs):
    buf = io.StringIO()
    buf.write("﻿")  # Excel opens UTF-8 (Arabic) correctly with the BOM
    w = csv.writer(buf)
    w.writerow([h for _, h in COLUMNS] + ["Unverified info (JSON)"])
    for p in qs:
        w.writerow([_safe(_value(p, f)) for f, _ in COLUMNS] + [json.dumps(p.unverified or [], ensure_ascii=False)])
    return buf.getvalue().encode("utf-8")


def export_xlsx(qs):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    wb = Workbook()
    ws = wb.active
    ws.title = "Companies"
    head_font, head_fill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="0B2545")
    ws.append([h for _, h in COLUMNS])
    us = wb.create_sheet("Unverified info")
    us.append(["Country", "Company", "Website"] + [h for _, h in UNV_COLUMNS])
    for sheet in (ws, us):
        for c in sheet[1]:
            c.font, c.fill = head_font, head_fill
        sheet.freeze_panes = "B2"
    for p in qs:
        ws.append([_safe(_value(p, f)) for f, _ in COLUMNS])
        for e in p.unverified or []:
            kind = "Person" if e.get("type") == "person" else "Company channel"
            us.append([_safe(x) for x in [p.country, p.name, p.website, kind] + [e.get(k, "") for k, _ in UNV_COLUMNS[1:]]])
    for sheet, widths in ((ws, {"A": 30, "J": 28, "K": 28, "N": 18, "X": 50}), (us, {"B": 30, "E": 26, "F": 24, "G": 28, "I": 40})):
        for col, w in widths.items():
            sheet.column_dimensions[col].width = w
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
