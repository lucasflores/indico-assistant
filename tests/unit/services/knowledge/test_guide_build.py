"""The guide copy's build (spec 022, T001): pages split by heading, embedded, written with a manifest."""

import json

import numpy as np

from indico_assistant.services.knowledge import guide_build


def _tree(tmp_path):
    docs = tmp_path / "docs"
    (docs / "meetings").mkdir(parents=True)
    (docs / "conferences" / "papers").mkdir(parents=True)
    (docs / "index.md").write_text("# Introduction\n\nWelcome to Indico. ![logo](assets/logo.png)\n")
    long_section = "\n\n".join(f"Paragraph {i} " + "word " * 60 for i in range(8))  # ~500 words
    (docs / "meetings" / "timetable.md").write_text(
        "# Making a Timetable\n\nOpen the <b>Timetable</b> page of your meeting.\n\n"
        "## Adding a break\n\n" + long_section + "\n\n### Tiny\n\nok\n")
    (docs / "conferences" / "papers" / "index.md").write_text("# Papers\n\nAbout paper reviewing in conferences.\n")
    return docs


def _fake_embed(texts):
    return np.array([[len(t) % 7 + 1.0, 1.0, 0.0, 2.0] for t in texts], dtype=np.float32)


def test_page_urls():
    assert guide_build.page_url("index.md") == "https://learn.getindico.io/"
    assert guide_build.page_url("meetings/timetable.md") == "https://learn.getindico.io/meetings/timetable/"
    assert guide_build.page_url("conferences/papers/index.md") == "https://learn.getindico.io/conferences/papers/"


def test_chunks_follow_headings_and_drop_markup(tmp_path):
    pages, chunks = guide_build.chunk_pages(_tree(tmp_path))
    assert pages == ["https://learn.getindico.io/", "https://learn.getindico.io/conferences/papers/",
                     "https://learn.getindico.io/meetings/timetable/"]
    titles = [c["title"] for c in chunks]
    assert "Making a Timetable" in titles and "Making a Timetable › Adding a break" in titles
    assert all("![" not in c["text"] and "<b>" not in c["text"] for c in chunks)
    breaks = [c for c in chunks if c["title"] == "Making a Timetable › Adding a break"]
    assert len(breaks) == 2  # the ~500-word section is split
    assert all(len(c["text"].split()) <= guide_build.MAX_WORDS + 70 for c in breaks)
    assert not any(c["title"].endswith("› Tiny") for c in chunks)  # a two-word section is dropped


def test_build_writes_the_copy(tmp_path):
    out = tmp_path / "out"
    manifest = guide_build.build(_tree(tmp_path), commit="abc1234", embed=_fake_embed, model="fake/model", out_dir=out)
    assert manifest["commit"] == "abc1234" and manifest["model"] == "fake/model" and manifest["dims"] == 4
    assert manifest["repo"] == guide_build.REPO and manifest["chunks"] == len(json.loads((out / "chunks.json").read_text()))
    assert json.loads((out / "manifest.json").read_text()) == manifest
    vectors = np.load(out / "vectors.npy")
    assert vectors.dtype == np.float32 and vectors.shape == (manifest["chunks"], 4)
    assert np.allclose(np.linalg.norm(vectors, axis=1), 1.0)  # normalised, so a dot product is the cosine


def test_cli_builds_from_the_commit(tmp_path, monkeypatch):
    from unittest.mock import MagicMock

    from click.testing import CliRunner

    from indico_assistant import cli
    from indico_assistant.services.embedding import service as embedding

    docs = _tree(tmp_path)
    model = MagicMock()
    model.encode.side_effect = lambda texts, **kw: _fake_embed(texts)
    monkeypatch.setattr(embedding, "load_model", lambda name: (model, 4))
    monkeypatch.setattr(guide_build, "fetch", lambda commit, dest: docs)
    monkeypatch.setattr(guide_build, "OUT_DIR", tmp_path / "out")
    result = CliRunner().invoke(cli.cli, ["guide-build", "--commit", "abc1234"])
    assert result.exit_code == 0, result.output
    assert "Guide abc1234: 3 pages" in result.output
    assert json.loads((tmp_path / "out" / "manifest.json").read_text())["commit"] == "abc1234"
