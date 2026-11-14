"""Practice areas ("labs"): one list shared by the site's "lab" entries, the enquiry form's area of interest, the CRM
deal field "lab" and the CRM reports. Change these to match your own services (keys are stored on deals; keep them
short and lowercase). Arabic names for the dashboard live in cms/ui_i18n.py and crm/ui_ar.py.
"""
AREAS = {"websites": "Websites", "content": "Content", "marketing": "Marketing", "support": "Support"}

# first letter of a service code -> area key, e.g. W1 -> websites (used when a prospect is moved to the pipeline)
AREA_OF_PREFIX = {"W": "websites", "C": "content", "M": "marketing", "S": "support"}

# values the enquiry form may send as "area of interest"
INTEREST_CHOICES = ["", *AREAS.values(), "Not sure yet"]
