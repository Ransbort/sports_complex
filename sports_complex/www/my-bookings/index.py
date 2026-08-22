# Copyright (c) 2026, Your Company and contributors
# For license information, please see license.txt

import frappe

from sports_complex.sports_complex.theme import get_theme_context


def get_context(context):
	context.title = "My Bookings"
	# Same reasoning as book-facility/index.py: no require_portal_login() here
	# - a guest who booked without an account still needs a way to look up
	# their own bookings, via the email-OTP identity check list_my_
	# bookings() itself enforces. The Vue app branches on window.isGuest to
	# show the email/OTP form only when there's no session identity to use
	# instead.
	context.is_guest = frappe.session.user == "Guest"
	context.update(get_theme_context())
	return context
