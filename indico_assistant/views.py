"""The plugin's page wrappers (spec 021): its templates inside Indico's profile and admin layouts."""

from indico.core.plugins import WPJinjaMixinPlugin
from indico.modules.admin.views import WPAdmin
from indico.modules.users.views import WPUser


class WPReports(WPJinjaMixinPlugin, WPUser):
    """A page in the user's profile (``templates/`` extending ``users/base.html``)."""


class WPReportsAdmin(WPJinjaMixinPlugin, WPAdmin):
    """A page in Indico's admin area (``templates/`` extending ``admin/base.html``)."""
