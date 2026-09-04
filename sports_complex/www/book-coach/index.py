# Copyright (c) 2026, Sports Complex and contributors
# For license information, please see license.txt

"""Book a Coach - public coaching-session booking page. Same shape as
www/book-facility/index.py: no require_portal_login() (guest booking via
emailed OTP is the point - see doctype/training_session/training_session.py's
create_guest_training_booking()), facilities/coaches list embedded
server-side rather than fetched, currency resolved server-side for the
same reason book-facility's own index.py does (a guest session's client-
side Currency-doc cache isn't reliably populated).
"""

import frappe

from sports_complex.sports_complex.doctype.training_session.training_session import list_bookable_coaches
from sports_complex.sports_complex.theme import get_theme_context


def get_context(context):
	context.title = "Book a Coach"
	context.is_guest = frappe.session.user == "Guest"
	context.coaches_json = frappe.as_json(list_bookable_coaches())

	currency = frappe.defaults.get_global_default("currency") or "USD"
	context.currency_symbol_json = frappe.as_json(
		frappe.db.get_value("Currency", currency, "symbol") or currency
	)

	context.update(get_theme_context())
	return context
