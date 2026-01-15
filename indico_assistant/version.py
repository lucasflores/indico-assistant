"""Version checking utilities for the Indico Assistant plugin.

Ensures the plugin only runs on compatible Indico versions.
"""

from packaging.version import Version

MINIMUM_INDICO_VERSION = "3.3"


def check_indico_version() -> None:
    """Check that the running Indico version meets minimum requirements.

    Raises:
        RuntimeError: If Indico version is below minimum required version.
    """
    try:
        import indico

        current_version = Version(indico.__version__)
    except ImportError as e:
        raise RuntimeError(
            "Indico Assistant requires Indico to be installed. "
            "Please install Indico before using this plugin."
        ) from e
    except Exception as e:
        raise RuntimeError(f"Failed to determine Indico version: {e}") from e

    minimum_version = Version(MINIMUM_INDICO_VERSION)

    if current_version < minimum_version:
        raise RuntimeError(
            f"Indico Assistant requires Indico {MINIMUM_INDICO_VERSION}+, "
            f"but found {indico.__version__}. "
            f"Please upgrade Indico to use this plugin."
        )


def get_indico_version() -> str:
    """Get the current Indico version string.

    Returns:
        The Indico version string, or 'unknown' if not determinable.
    """
    try:
        import indico

        return indico.__version__
    except Exception:
        return "unknown"
