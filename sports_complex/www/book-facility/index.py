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
	context.update(get_theme_context())
	return context
