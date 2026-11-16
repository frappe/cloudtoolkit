import frappe
from frappe.installer import remove_from_installed_apps

LEGACY_APP = "pipeline"


def before_install() -> None:
	"""Adopt the modules of the `pipeline` app this app was renamed from, so its tables and rows stay."""
	if LEGACY_APP not in frappe.get_installed_apps():
		return

	frappe.db.set_value("Module Def", {"app_name": LEGACY_APP}, "app_name", "cloudtoolkit")
	remove_from_installed_apps(LEGACY_APP)
