"""Links in a knowledge answer, checked by code after the model wrote them (spec 022, FR-012 and FR-016).

A link to this Indico must be a page of the user's page list; it is rebased onto the instance's address, whatever host
the model put in front of the path, except the home page "/", which every site has (``[Google](https://google.com/)``
is not a link to this Indico). A guide link must be a page of the shipped copy. Anything else loses its link: a
markdown link keeps its label, a bare URL and a reference definition (``[1]: /admin/``) are removed. Paths are
relative to BASE_URL, which can have a path of its own (``https://host/indico``). (Raw HTML links are not checked:
the chat shows HTML as text, never as a link.)
"""

import re
from urllib.parse import urlsplit

GUIDE_HOST = "learn.getindico.io"
KEPT_HOSTS = {"docs.getindico.io"}  # Indico's admin documentation: linked as it is, not checked page by page
_URL = r"(?:[^\s()<>]|\([^\s()<>]*\))+"  # (one level of parentheses: Wikipedia's "Pion_(particle)")
_BARE = r"https?://(?:[^\s()<>\]]|\([^\s()<>]*\))+"
_TITLE = r'(?:\s+"[^"]*")?'
_LINK = re.compile(rf"\[([^\]]+)\]\(\s*<?({_URL})>?{_TITLE}\s*\)"  # [label](url "title")
                   rf"|( ?)({_BARE})"  # a bare URL
                   rf"|^( {{0,3}}\[[^\]]+\]:[ \t]*)<?({_URL})>?{_TITLE}[ \t]*$", re.M | re.I)  # [1]: url "title"


#: Any link target, whatever its label (``](url "title")``): the strict pass, for labels the link pattern can't parse
_TARGET = re.compile(rf"\]\(\s*<?({_URL}|)>?{_TITLE}\s*\)", re.I)


def _local(path, root):
    """``path`` relative to BASE_URL's own path (``/indico/event/5/`` -> ``/event/5/`` under ``/indico``)."""
    return path[len(root):] if root and (path == root or path.startswith(root + "/")) else path


def found_in(texts, base_url):
    """(paths of this Indico, guide pages) linked in ``texts``: what a chat answer may link again."""
    host, root = urlsplit(base_url).netloc, urlsplit(base_url).path.rstrip("/")
    paths, guide = set(), set()
    for text in texts:
        for match in _LINK.finditer(text or ""):
            url = (match.group(2) or match.group(4) or match.group(6)).rstrip(".,;:!?")
            parts = urlsplit(url)
            if parts.netloc == GUIDE_HOST:
                guide.add(f"https://{GUIDE_HOST}{_key(parts.path) if _key(parts.path) != '/' else ''}/")
            elif parts.path.startswith("/") and parts.netloc in ("", host):
                paths.add(_local(parts.path, root))
    return paths, guide


def _key(path):
    return path.rstrip("/") or "/"


def check(text, pages, guide_urls, base_url, urls=(), strict=False):
    """``text`` with every link checked. ``pages``: paths the user can open; ``guide_urls``: the copy's pages;
    ``urls``: addresses kept exactly as they are, whatever their fragment (a connector answer's GitHub items, spec
    023 FR-017: only what its tools returned, so a text read on GitHub can't plant a link); ``strict``: no other
    site's links either (Indico's docs site is kept for the knowledge answer, not page by page)."""
    known = {_key(p): p for p in pages}
    exact = {u.split("#")[0] for u in urls}
    base = base_url.rstrip("/")
    host, root = urlsplit(base).netloc, urlsplit(base).path

    def resolve(url):
        if url.split("#")[0] in exact:
            return url
        parts = urlsplit(url)
        anchor = f"#{parts.fragment}" if parts.fragment else ""
        if parts.netloc == GUIDE_HOST:
            page = f"https://{GUIDE_HOST}{_key(parts.path) if _key(parts.path) != '/' else ''}/"
            return url if page in guide_urls else None
        if parts.netloc in KEPT_HOSTS and not strict:
            return url
        if parts.netloc not in ("", host) and _key(parts.path) == "/":
            return None
        path = _local(parts.path, root) if parts.netloc in ("", host) else parts.path
        if path.startswith("/") and (page := known.get(_key(path))):
            return base + page + anchor
        return None

    def replace(match):
        label, url, space, bare, ref, target = match.groups()
        if ref is not None:
            return f"{ref}{new}" if (new := resolve(target)) else ""
        if url is not None:
            return f"[{label}]({new})" if (new := resolve(url)) else label
        trail = re.search(r"[.,;:!?]+$", bare)
        bare, tail = (bare[:trail.start()], trail.group()) if trail else (bare, "")
        return f"{space}{new}{tail}" if (new := resolve(bare)) else tail

    text = _LINK.sub(replace, text)
    if strict:  # (fresh-review: a label holding brackets hides its link from _LINK; every target is checked alone)
        text = _TARGET.sub(lambda m: f"]({new})" if m.group(1) and (new := resolve(m.group(1))) else "]", text)
    return text


def strip_images(text):
    """No markdown image survives: an image is fetched as soon as the answer is shown, so its address could carry
    private text away (spec 023 FR-017). Every image marker becomes a plain link, which ``check`` then keeps or
    drops like any other, whatever the alt text holds (Copilot, PR #17: nested brackets slipped past a regex)."""
    return re.sub(r"!+\[", "[", text)
