"""The user-guide copy the plugin ships, searched locally (spec 022, FR-013, FR-014, FR-016).

Loaded once per process. Questions are embedded with the copy's own model (its manifest says which), through the
embedding service's shared model cache: when the plugin's ``embedding_model`` setting names the same model, the one
loaded copy serves both. Anything wrong (no copy, a model that cannot load, dimensions that do not match) makes the
guide unavailable, never an exception: knowledge answers then come from the capability and page lists alone.
"""

import functools
import json
import logging
import threading
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)


class Guide:
    def __init__(self, directory):
        self._dir = Path(directory)
        self._lock = threading.Lock()
        self._loaded = False
        self.problem = None
        self.manifest, self._chunks, self._vectors, self._model = {}, [], None, None

    def _load(self):
        with self._lock:
            if self._loaded:
                return
            self._loaded = True
            try:
                from indico_assistant.services.embedding import service as embedding

                manifest, chunks, vectors = self._read()
                model, dims = embedding.load_model(manifest["model"])
                if dims != manifest["dims"]:
                    raise ValueError(f"{manifest['model']} gives {dims} dimensions, the index has {manifest['dims']}")
            except Exception as exc:  # the guide is an enhancement: a knowledge answer comes without it
                self.problem = f"guide copy unavailable: {exc}"
                logger.warning(self.problem)
                return
            self.manifest, self._chunks, self._vectors, self._model = manifest, chunks, vectors, model

    def _read(self):
        manifest = json.loads((self._dir / "manifest.json").read_text())
        chunks = json.loads((self._dir / "chunks.json").read_text())
        vectors = np.load(self._dir / "vectors.npy")
        if vectors.shape != (len(chunks), manifest["dims"]):
            raise ValueError(f"the index holds {vectors.shape}, the manifest says {len(chunks)} x {manifest['dims']}")
        return manifest, chunks, vectors

    def describe(self):
        """The copy's state from its files alone, for the health check (which runs in the web process: the model is
        only loaded where questions are answered, in the worker)."""
        try:
            manifest, _, _ = self._read()
        except Exception as exc:
            return {"ok": False, "problem": f"guide copy unavailable: {exc}"}
        return {"ok": True, "guide_commit": manifest["commit"], "pages": len(manifest["pages"]),
                "model": manifest["model"]}

    @property
    def ok(self):
        self._load()
        return self.problem is None

    @property
    def commit(self):
        self._load()
        return self.manifest.get("commit")

    @property
    def page_urls(self):
        self._load()
        return set(self.manifest.get("pages", ()))

    def excerpts(self, question, k=6):
        """The ``k`` pieces nearest to ``question``: [{url, title, text, score}], nearest first; [] if unavailable."""
        if not self.ok:
            return []
        try:
            query = self._model.encode([question], normalize_embeddings=True)[0]
            scores = self._vectors @ query
        except Exception as exc:  # inference failed (memory, say): this answer comes from the two lists alone
            logger.warning("guide search failed: %s", exc)  # (not self.problem: the next question may work)
            return []
        return [self._chunks[i] | {"score": round(float(scores[i]), 4)} for i in np.argsort(-scores)[:k]]


_guide = None


def get_guide():
    """The shipped copy, one per process."""
    global _guide
    if _guide is None:
        from indico_assistant.services.knowledge.guide_build import OUT_DIR

        _guide = Guide(OUT_DIR)
    return _guide


@functools.lru_cache(maxsize=4)
def _described(directory):
    """(the shipped files do not change while a process runs: read once, not on every health request)"""
    return Guide(directory).describe()


def status(settings):
    """The knowledge route's state for the health check: the guide copy's files and which gate decides."""
    from indico_assistant.services.knowledge.guide_build import OUT_DIR

    return {**_described(OUT_DIR), "gate": "jev" if settings.get("jev_api_key") else "classifier only"}
