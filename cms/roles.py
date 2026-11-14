"""Dashboard roles.

admin   superuser: everything, including users, settings and plugins
editor  staff: pages, collections, media, menus, inbox; publishes
author  staff in the "author" group: writes posts in AUTHOR_COLLECTIONS, saves drafts and submits them
        for review; cannot publish, delete or touch other content
sales   staff in the "sales" group: CRM, website enquiries and stats; no access to content
"""
AUTHOR_GROUP = "author"
SALES_GROUP = "sales"
AUTHOR_COLLECTIONS = {"post"}
ROLES = ("admin", "editor", "author", "sales")


def role_of(user):
    if not user or not user.is_authenticated:
        return None
    if user.is_superuser:
        return "admin"
    if not user.is_staff:
        return None
    groups = set(user.groups.values_list("name", flat=True))
    if AUTHOR_GROUP in groups:
        return "author"
    if SALES_GROUP in groups:
        return "sales"
    return "editor"


def is_author(user):
    return role_of(user) == "author"


def is_sales(user):
    return role_of(user) == "sales"


def set_role(user, role):
    """Apply a role to a saved user (admin / editor / author / sales)."""
    from django.contrib.auth.models import Group
    user.is_staff = True
    user.is_superuser = role == "admin"
    user.save(update_fields=["is_staff", "is_superuser"])
    for name, wanted in ((AUTHOR_GROUP, role == "author"), (SALES_GROUP, role == "sales")):
        group, _ = Group.objects.get_or_create(name=name)
        (user.groups.add if wanted else user.groups.remove)(group)


def can_edit_entry(user, entry):
    """Authors edit only their own entries in author collections, and only until an editor publishes them."""
    if not is_author(user):
        return True
    return entry.collection in AUTHOR_COLLECTIONS and entry.created_by_id == user.pk and not entry.is_published
