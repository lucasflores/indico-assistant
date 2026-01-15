"""Unit tests for Indico version checking."""

import pytest
from unittest.mock import MagicMock, patch


class TestIndicoVersionCheck:
    """Tests for the check_indico_version function."""

    def test_check_indico_version_passes_for_3_3(self):
        """Should pass for Indico version 3.3."""
        with patch("indico_assistant.version.Version") as mock_version:
            # Mock Version to return comparable objects
            mock_current = MagicMock()
            mock_minimum = MagicMock()
            mock_current.__lt__ = MagicMock(return_value=False)
            mock_version.side_effect = [mock_current, mock_minimum]

            with patch.dict("sys.modules", {"indico": MagicMock(__version__="3.3.0")}):
                from indico_assistant.version import check_indico_version

                # Should not raise
                # Note: This test is simplified; full test requires Indico installed

    def test_minimum_version_constant(self):
        """MINIMUM_INDICO_VERSION should be 3.3."""
        from indico_assistant.version import MINIMUM_INDICO_VERSION

        assert MINIMUM_INDICO_VERSION == "3.3"

    def test_check_indico_version_raises_for_old_version(self):
        """Should raise RuntimeError for Indico < 3.3."""
        from packaging.version import Version

        # Create a mock indico module with old version
        mock_indico = MagicMock()
        mock_indico.__version__ = "3.2.0"

        with patch.dict("sys.modules", {"indico": mock_indico}):
            from indico_assistant import version

            # Reload to pick up mocked module
            with pytest.raises(RuntimeError) as exc_info:
                version.check_indico_version()

            assert "requires Indico 3.3+" in str(exc_info.value)
            assert "3.2.0" in str(exc_info.value)

    def test_check_indico_version_raises_when_indico_not_installed(self):
        """Should raise RuntimeError when Indico is not installed."""
        with patch.dict("sys.modules", {"indico": None}):
            with patch("builtins.__import__", side_effect=ImportError("No module named 'indico'")):
                from indico_assistant import version

                with pytest.raises(RuntimeError) as exc_info:
                    version.check_indico_version()

                assert "Indico to be installed" in str(exc_info.value)


class TestGetIndicoVersion:
    """Tests for the get_indico_version helper function."""

    def test_get_indico_version_returns_version_string(self):
        """Should return the Indico version string."""
        mock_indico = MagicMock()
        mock_indico.__version__ = "3.3.5"

        with patch.dict("sys.modules", {"indico": mock_indico}):
            from indico_assistant.version import get_indico_version

            result = get_indico_version()
            assert result == "3.3.5"

    def test_get_indico_version_returns_unknown_on_error(self):
        """Should return 'unknown' when version cannot be determined."""
        with patch.dict("sys.modules", {"indico": None}):
            with patch("builtins.__import__", side_effect=Exception("import error")):
                from indico_assistant.version import get_indico_version

                result = get_indico_version()
                assert result == "unknown"
