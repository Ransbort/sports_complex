# Copyright (c) 2026, Your Company
# License: MIT

import frappe
from frappe.model.document import Document


class SportsComplexSetup(Document):
	pass


def get_settings():
	"""Convenience accessor, e.g.:
	from sports_complex.sports_complex.sports_complex_settings.doctype.sports_complex_setup.sports_complex_setup import get_settings
	settings = get_settings()
	if settings.require_payment_before_confirmation: ...
	"""
	return frappe.get_cached_doc("Sports Complex Setup")
