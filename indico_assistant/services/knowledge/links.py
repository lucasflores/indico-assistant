"""Links in a knowledge answer, checked by code after the model wrote them (spec 022, FR-012 and FR-016).

A link to this Indico must be a page of the user's page list; it is rebased onto the instance's address, whatever host
the model put in front of the path. A guide link must be a page of the shipped copy. Anything else loses its link:
a markdown link keeps its label, a bare URL is removed.
"""

import re
from urllib.parse import urlsplit

GUIDE_HOST = "learn.getindico.io"
KEPT_HOSTS = {"docs.getindico.io"}  # Indico's admin documentation: linked as it is, not checked page by page
_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)|( ?)(https?://[^\s)\]<>]+)")


def _key(path):
    return path.rstrip("/") or "/"


def check(text, pages, guide_urls, base_url):
    """``text`` with every link checked. ``pages``: paths the user can open; ``guide_urls``: the copy's pages."""
    known = {_key(p): p for p in pages}
    base = base_url.rstrip("/")

    def resolve(url):
        parts = urlsplit(url)
        anchor = f"#{parts.fragment}" if parts.fragment else ""
        if parts.netloc == GUIDE_HOST:
            page = f"https://{GUIDE_HOST}{_key(parts.path) if _key(parts.path) != '/' else ''}/"
            return url if page in guide_urls else None
        if parts.netloc in KEPT_HOSTS:
            return url
        if parts.path.startswith("/") and (page := known.get(_key(parts.path))):
            return base + page + anchor
        return None

    def replace(match):
        label, url, space, bare = match.groups()
        if url is not None:
            return f"[{label}]({new})" if (new := resolve(url)) else label
        trail = re.search(r"[.,;:!?]+$", bare)
        bare, tail = (bare[:trail.start()], trail.group()) if trail else (bare, "")
        return f"{space}{new}{tail}" if (new := resolve(bare)) else tail

    return _LINK.sub(replace, text)
