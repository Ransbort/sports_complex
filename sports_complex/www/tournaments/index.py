# Copyright (c) 2026, Sports Complex and contributors
# For license information, please see license.txt

"""Register for a Tournament - public tournament entry page. Same shape
as www/book-facility/index.py and www/book-coach/index.py: no
require_portal_login(), tournament list embedded server-side, currency
resolved server-side.
"""

import frappe

from sports_complex.sports_complex.doctype.tournament_registration.tournament_registration import (
	list_open_tournaments,
)
from sports_complex.sports_complex.theme import get_theme_context


def get_context(context):
	context.title = "Register for a Tournament"
	context.is_guest = frappe.session.user == "Guest"
	context.tournaments_json = frappe.as_json(list_open_tournaments())

	currency = frappe.defaults.get_global_default("currency") or "USD"
	context.currency_symbol_json = frappe.as_json(
		frappe.db.get_value("Currency", currency, "symbol") or currency
	)

	context.update(get_theme_context())
	return context
