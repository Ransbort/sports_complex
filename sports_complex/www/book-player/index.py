# Copyright (c) 2026, Sports Complex and contributors
# For license information, please see license.txt

"""Book a Player - public 1-on-1-with-a-roster-Player booking page. Same
shape as www/book-coach/index.py (which is itself modeled on www/book-
facility/index.py): no require_portal_login() (guest booking via emailed
OTP is the point - see doctype/player_session/player_session.py's
create_guest_player_booking()), players list embedded server-side rather
than fetched, currency resolved server-side for the same reason book-
facility's own index.py does (a guest session's client-side Currency-doc
cache isn't reliably populated).
"""

import frappe

from sports_complex.sports_complex.doctype.player_session.player_session import list_bookable_players
from sports_complex.sports_complex.theme import get_theme_context


def get_context(context):
	context.title = "Book a Player"
	context.is_guest = frappe.session.user == "Guest"
	context.players_json = frappe.as_json(list_bookable_players())

	currency = frappe.defaults.get_global_default("currency") or "USD"
	context.currency_symbol_json = frappe.as_json(
		frappe.db.get_value("Currency", currency, "symbol") or currency
	)

	context.update(get_theme_context())
	return context
