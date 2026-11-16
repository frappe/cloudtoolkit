from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from cloudtoolkit.install import LEGACY_APP, before_install

MODULE = "cloudtoolkit.install"


class IntegrationTestInstall(IntegrationTestCase):
	"""Taking over the modules of the renamed `pipeline` app."""

	def test_adopts_the_legacy_module_and_drops_the_legacy_app(self):
		frappe.db.set_value("Module Def", "Pipeline", "app_name", LEGACY_APP)

		with (
			patch(f"{MODULE}.frappe.get_installed_apps", return_value=["frappe", LEGACY_APP]),
			patch(f"{MODULE}.remove_from_installed_apps") as remove,
		):
			before_install()

		self.assertEqual(frappe.db.get_value("Module Def", "Pipeline", "app_name"), "cloudtoolkit")
		remove.assert_called_once_with(LEGACY_APP)

	def test_does_nothing_on_a_fresh_site(self):
		with (
			patch(f"{MODULE}.frappe.get_installed_apps", return_value=["frappe"]),
			patch(f"{MODULE}.remove_from_installed_apps") as remove,
		):
			before_install()

		remove.assert_not_called()
