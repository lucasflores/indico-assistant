"""Spec 024 (FR-022): the Langfuse integration is gone, and nothing brings it back by an import."""

import re
from pathlib import Path

import indico_assistant

IMPORT = re.compile(r'^\s*(from|import)\s+(langfuse\b|indico_assistant\.services\.observability\b)', re.MULTILINE)


def test_no_module_imports_langfuse_or_the_old_observability_package():
    root = Path(indico_assistant.__file__).parent
    found = [str(path.relative_to(root)) for path in root.rglob('*.py') if IMPORT.search(path.read_text())]
    assert found == []
    assert not (root / 'services' / 'observability').exists()
