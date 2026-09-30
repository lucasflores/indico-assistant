"""The user-guide copy the plugin ships, searched locally (spec 022, FR-013, FR-014, FR-016).

Loaded once per process. Questions are embedded with the copy's own model (its manifest says which), through the
embedding service's shared model cache: when the plugin's ``embedding_model`` setting names the same model, the one
loaded copy serves both. Anything wrong (no copy, a model that cannot load, dimensions that do not match) makes the
guide unavailable, never an exception: knowledge answers then come from the capability and page lists alone.
"""

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

                manifest = json.loads((self._dir / "manifest.json").read_text())
                chunks = json.loads((self._dir / "chunks.json").read_text())
                vectors = np.load(self._dir / "vectors.npy")
                if vectors.shape != (len(chunks), manifest["dims"]):
                    raise ValueError(f"the index holds {vectors.shape}, the manifest says {len(chunks)} x "
                                     f"{manifest['dims']}")
                model, dims = embedding.load_model(manifest["model"])
                if dims != manifest["dims"]:
                    raise ValueError(f"{manifest['model']} gives {dims} dimensions, the index has {manifest['dims']}")
            except Exception as exc:  # the guide is an enhancement: a knowledge answer comes without it
                self.problem = f"guide copy unavailable: {exc}"
                logger.warning(self.problem)
                return
            self.manifest, self._chunks, self._vectors, self._model = manifest, chunks, vectors, model

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
        query = self._model.encode([question], normalize_embeddings=True)[0]
        scores = self._vectors @ query
        return [self._chunks[i] | {"score": round(float(scores[i]), 4)} for i in np.argsort(-scores)[:k]]


_guide = None


def get_guide():
    """The shipped copy, one per process."""
    global _guide
    if _guide is None:
        from indico_assistant.services.knowledge.guide_build import OUT_DIR

        _guide = Guide(OUT_DIR)
    return _guide
