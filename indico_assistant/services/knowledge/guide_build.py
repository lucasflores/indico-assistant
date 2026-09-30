"""Build the guide copy the plugin ships (spec 022, FR-013 to FR-015).

Indico's user guide (learn.getindico.io, built from ``indico/indico-user-docs``) at one pinned commit, split by
heading and embedded with one pinned model. Run for a release with ``indico assistant guide-build --commit <sha>``;
answering a question never needs the network.
"""

import io
import json
import re
import tarfile
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

REPO = "indico/indico-user-docs"
LEARN = "https://learn.getindico.io/"
MODEL = "BAAI/bge-small-en-v1.5"
MAX_WORDS = 350  # a piece of guide text, at most (bge-small reads 512 tokens)
OUT_DIR = Path(__file__).resolve().parents[2] / "knowledge_guide"

_HEADING = re.compile(r"^(#{1,4})\s+(.+?)\s*$", re.M)


def page_url(relative):
    """``meetings/timetable.md`` -> its learn.getindico.io address (MkDocs directory URLs)."""
    path = Path(relative).with_suffix("")
    parts = path.parts[:-1] if path.name == "index" else path.parts
    return LEARN + "".join(f"{p}/" for p in parts)


def _clean(text):
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)  # screenshots
    text = re.sub(r"<[^>]+>", "", text)  # html
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def chunk_pages(docs_dir):
    """(sorted page URLs, [{url, title, text}]): one piece per heading section, long sections split on paragraphs."""
    docs_dir = Path(docs_dir)
    pages, chunks = [], []
    for path in sorted(docs_dir.rglob("*.md")):
        url, text = page_url(path.relative_to(docs_dir)), _clean(path.read_text())
        pages.append(url)
        page_title = next((m.group(2) for m in _HEADING.finditer(text) if m.group(1) == "#"), path.stem)
        for section in re.split(r"^(?=#{1,4}\s)", text, flags=re.M):
            heading = _HEADING.match(section)
            title = page_title if not heading or heading.group(2) == page_title else f"{page_title} › {heading.group(2)}"
            body, buf = (section[heading.end():] if heading else section).strip(), []
            for para in [p for p in body.split("\n\n") if p.strip()]:
                if buf and len(" ".join(buf + [para]).split()) > MAX_WORDS:
                    chunks.append({"url": url, "title": title, "text": "\n\n".join(buf)})
                    buf = []
                buf.append(para)
            if buf and len(" ".join(buf).split()) > 5:
                chunks.append({"url": url, "title": title, "text": "\n\n".join(buf)})
    return sorted(set(pages)), chunks


def build(docs_dir, *, commit, embed, model=MODEL, out_dir=None):
    """Write manifest.json, chunks.json and vectors.npy into ``out_dir``; returns the manifest."""
    pages, chunks = chunk_pages(docs_dir)
    vectors = np.asarray(embed([f"{c['title']}\n{c['text']}" for c in chunks]), dtype=np.float32)
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
    manifest = {"repo": REPO, "commit": commit, "built_at": datetime.now(UTC).isoformat(timespec="seconds"),
                "model": model, "dims": int(vectors.shape[1]), "chunks": len(chunks), "pages": pages}
    out_dir = Path(out_dir or OUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    np.save(out_dir / "vectors.npy", vectors)
    (out_dir / "chunks.json").write_text(json.dumps(chunks, ensure_ascii=False, indent=0))
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=1))
    return manifest


def fetch(commit, dest):
    """Download the guide's source at ``commit`` into ``dest``; returns its ``docs`` directory."""
    url = f"https://codeload.github.com/{REPO}/tar.gz/{commit}"
    with urllib.request.urlopen(url, timeout=60) as response:  # noqa: S310 (a fixed https host)
        data = response.read()
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        tar.extractall(dest, filter="data")
    (root,) = [p for p in Path(dest).iterdir() if p.is_dir()]
    return root / "docs"
