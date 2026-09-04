# Copyright (c) 2026, Your Company and contributors
# For license information, please see license.txt

import frappe

from sports_complex.sports_complex.doctype.facility_booking.facility_booking import (
	list_bookable_facilities,
)
from sports_complex.sports_complex.theme import get_theme_context


def get_context(context):
	context.title = "Book a Facility"
	# Deliberately no require_portal_login() here (contrast my-payments/
	# my-payment in frappe_paystack) - this page has to work for a guest
	# too, since guest booking (email OTP, no account) is the whole point
	# of create_guest_booking(). The Vue app branches on window.isGuest
	# to show the right form.
	context.is_guest = frappe.session.user == "Guest"
	context.facilities_json = frappe.as_json(list_bookable_facilities())

	# Prices used to render as a bare number ("150.00 / hour") with no
	# currency at all. Sports Complex Setup has its own default_currency
	# field, but nothing in this app actually reads it - every other
	# money display here (Cashier, Trial Registration Cashier) instead
	# goes through frappe.defaults.get_global_default('currency'), the
	# site's own default - so this follows that same convention rather
	# than introducing a second, disconnected source of truth. Resolved
	# to a symbol server-side (frappe.db.get_value) rather than leaning
	# on the client-side format_currency()/Currency-doc cache, since a
	# guest session on a plain website page has no guarantee that cache
	# is populated the way a logged-in desk session's is.
	currency = frappe.defaults.get_global_default("currency") or "USD"
	context.currency_symbol_json = frappe.as_json(
		frappe.db.get_value("Currency", currency, "symbol") or currency
	)

	context.update(get_theme_context())
	return context
