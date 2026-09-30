"""The Indico pages one user can open, as Indico's own menus list them for that user (spec 022, FR-011).

The menus are built from Indico's menu signals, which check permissions, event features and installed plugins, so
the list is right for this user, this event, this instance and its version. Every link in a knowledge answer must
come from it (links.py).
"""

from collections import namedtuple

from flask import session

Page = namedtuple("Page", "title section path")


def _menu(menu_id, **kwargs):
    from indico.web.menu import build_menu_structure

    for entry in build_menu_structure(menu_id, **kwargs):
        for item in getattr(entry, "items", None) or [entry]:
            if (url := getattr(item, "url", None)) and url.startswith("/"):
                yield (entry.title if item is not entry else ""), item.title, url


def page_list(user, event=None):
    """[Page]: the event page and its management menu (when on an event page), the profile menu and the top menu
    (Room booking is there when the user may see it). Must run as ``user`` (``acting_as``): the menus read
    ``session.user``."""
    if session.user != user:
        raise RuntimeError(f"page_list({user}) must run as that user, not as {session.user}")
    pages = []
    if event is not None:
        if event.can_access(user):
            pages.append(Page("The event page", "", f"/event/{event.id}/"))
        pages += [Page(title, " › ".join(filter(None, ("event management", section))), url)
                  for section, title, url in _menu("event-management-sidemenu", event=event)]
    pages += [Page(title, "my profile", url) for _, title, url in _menu("user-profile-sidemenu", user=user)]
    pages += [Page(title, "top menu", url) for _, title, url in _menu("top-menu")]
    return pages


def render(pages, event=None):
    """The page list as the answer's prompt gets it."""
    lines = ["Pages of this Indico the user can open (link only to these, with the path exactly as given):"]
    lines += [f"- {p.section + ' › ' if p.section else ''}{p.title}: {p.path}" for p in pages]
    if event is not None and not any("/manage" in p.path for p in pages):
        lines.append("- (no management pages: they do not manage this event)")
    if not any(p.path == "/rooms/" for p in pages):
        lines.append("- Room booking is NOT available to them on this Indico.")
    return "\n".join(lines)
