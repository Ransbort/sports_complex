# Copyright (c) 2026, Your Company and contributors
# For license information, please see license.txt

import frappe

from sports_complex.sports_complex.doctype.facility_booking.facility_booking import (
	get_booking_status,
)
from sports_complex.sports_complex.theme import get_theme_context


def get_context(context):
	context.title = "Booking Confirmation"
	context.update(get_theme_context())

	booking_name = frappe.form_dict.get("booking")
	token = frappe.form_dict.get("token")

	# Fallback for /booking-confirmation/<name> links if the
	# website_route_rules entry (hooks.py) doesn't populate
	# form_dict.booking for some reason - same defensive pattern
	# frappe_paystack's paystack-checkout/my-payment pages use for their
	# own path-segment links.
	if not booking_name:
		path = frappe.local.request.path or ""
		parts = [p for p in path.split("/") if p]
		if parts and parts[-1] != "booking-confirmation":
			booking_name = parts[-1]

	context.booking_name = booking_name
	context.token = token
	context.doc = None

	if booking_name and frappe.db.exists("Facility Booking", booking_name):
		try:
			context.doc = get_booking_status(booking_name, token)
		except frappe.PermissionError:
			# context.doc stays None - same "not found" message either way,
			# so a guessed booking name can't be used to distinguish
			# someone else's booking from one that simply doesn't exist.
			pass

	context.doc_json = frappe.as_json(context.doc) if context.doc else "null"
	context.token_json = frappe.as_json(context.token) if context.token else "null"
	return context
