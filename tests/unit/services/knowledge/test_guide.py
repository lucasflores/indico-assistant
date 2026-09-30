"""The shipped guide copy: loaded once, searched with its own model, and never an exception (spec 022, FR-014/016)."""

import json

import numpy as np
import pytest

from indico_assistant.services.embedding import service as embedding
from indico_assistant.services.knowledge import guide_build
from indico_assistant.services.knowledge.guide import Guide

WORDS = ["timetable", "protection", "reminder", "survey"]


def _vector(text):
    """A fake embedding: one axis per topic word, so the nearest piece is the one naming the same topic."""
    v = np.array([float(w in text.lower()) for w in WORDS] + [0.1], dtype=np.float32)
    return v / np.linalg.norm(v)


class FakeModel:
    def __init__(self):
        self.calls = 0

    def encode(self, texts, **kwargs):
        self.calls += 1
        return np.stack([_vector(t) for t in texts])


@pytest.fixture
def copy_dir(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    for word in WORDS:
        (docs / f"{word}.md").write_text(f"# About the {word}\n\nHow to use the {word} page of your event, step by step.\n")
    out = tmp_path / "copy"
    guide_build.build(docs, commit="abc1234", embed=lambda texts: np.stack([_vector(t) for t in texts]),
                      model="fake/model", out_dir=out)
    return out


@pytest.fixture
def model(monkeypatch):
    fake, asked = FakeModel(), []
    monkeypatch.setattr(embedding, "load_model", lambda name: asked.append(name) or (fake, len(WORDS) + 1))
    fake.asked = asked
    return fake


def test_excerpts_are_the_nearest_pieces(copy_dir, model):
    guide = Guide(copy_dir)
    hits = guide.excerpts("How do I change the protection of my event?", k=2)
    assert hits[0]["url"] == "https://learn.getindico.io/protection/" and len(hits) == 2
    assert model.asked == ["fake/model"]  # the copy's own model, whatever the embedding_model setting says
    assert guide.ok and guide.commit == "abc1234" and "https://learn.getindico.io/survey/" in guide.page_urls


def test_loaded_once(copy_dir, model):
    guide = Guide(copy_dir)
    guide.excerpts("timetable")
    guide.excerpts("survey")
    assert model.asked == ["fake/model"]


def test_a_dimension_mismatch_is_unavailable_not_an_error(copy_dir, monkeypatch):
    monkeypatch.setattr(embedding, "load_model", lambda name: (FakeModel(), 384))
    guide = Guide(copy_dir)
    assert guide.excerpts("timetable") == []
    assert not guide.ok and "384" in guide.problem


def test_a_manifest_that_does_not_match_its_vectors(copy_dir, model):
    manifest = json.loads((copy_dir / "manifest.json").read_text())
    (copy_dir / "manifest.json").write_text(json.dumps({**manifest, "dims": 8}))
    guide = Guide(copy_dir)
    assert guide.excerpts("timetable") == [] and not guide.ok


def test_no_copy(tmp_path, model):
    guide = Guide(tmp_path / "missing")
    assert guide.excerpts("timetable") == [] and not guide.ok and guide.page_urls == set()


def test_a_model_that_cannot_load(copy_dir, monkeypatch):
    def fail(name):
        raise OSError("offline")
    monkeypatch.setattr(embedding, "load_model", fail)
    guide = Guide(copy_dir)
    assert guide.excerpts("timetable") == [] and "offline" in guide.problem


def test_describe_reads_the_files_without_loading_the_model(copy_dir, monkeypatch):
    """The health check runs in the web process: the model (375 MB) is only ever loaded in the worker."""
    def never(name):
        raise AssertionError("the model was loaded")
    monkeypatch.setattr(embedding, "load_model", never)
    from indico_assistant.services.knowledge.guide import status

    assert Guide(copy_dir).describe() == {"ok": True, "guide_commit": "abc1234", "pages": 4, "model": "fake/model"}
    assert not Guide(copy_dir.parent / "missing").describe()["ok"]
    monkeypatch.setattr("indico_assistant.services.knowledge.guide_build.OUT_DIR", copy_dir)
    assert status({"jev_api_key": "k"})["gate"] == "jev"
    assert status({})["gate"] == "classifier only"


def test_a_search_that_fails_is_unavailable_not_an_error(copy_dir, monkeypatch):
    """(Copilot, PR #15) the model loads, then encoding fails (out of memory, say): no excerpts, no crash"""
    class Broken(FakeModel):
        def encode(self, texts, **kwargs):
            raise RuntimeError("out of memory")
    monkeypatch.setattr(embedding, "load_model", lambda name: (Broken(), len(WORDS) + 1))
    guide = Guide(copy_dir)
    assert guide.excerpts("timetable") == [] and "out of memory" in guide.problem
