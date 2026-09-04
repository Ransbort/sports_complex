# Copyright (c) 2026, Your Company and contributors
# For license information, please see license.txt

from urllib.parse import quote

import frappe


def get_context(context):
	"""This page has moved into the Vue Portal (see frontend/src/pages/
	BookingConfirmation.vue) - /portal/booking-confirmation/<name> now
	renders it client-side, fed by the same get_booking_status() call
	this page used to make server-side.

	This route stays in place only so links already sent out (booking
	confirmation/reminder emails - see facility_booking.py's
	_send_booking_confirmation_email()/_send_booking_reminder_email(),
	both since updated to point new links straight at /portal/...) keep
	working: a plain redirect into the new URL, carrying the booking
	name and guest access token across unchanged. New links are no
	longer generated pointing here.

	Same "set flags.redirect_location + response['type'] = 'redirect'"
	pattern frappe_paystack's require_portal_login() and healthcare's
	patient-portal page already use in this codebase - not
	`raise frappe.Redirect`, which isn't a real API.
	"""
	booking_name = frappe.form_dict.get("booking")
	token = frappe.form_dict.get("token")

	# Fallback for /booking-confirmation/<name> links if the
	# website_route_rules entry (hooks.py) doesn't populate
	# form_dict.booking for some reason - same defensive pattern this
	# page already used before it became a pure redirect.
	if not booking_name:
		path = frappe.local.request.path or ""
		parts = [p for p in path.split("/") if p]
		if parts and parts[-1] != "booking-confirmation":
			booking_name = parts[-1]

	target = f"/portal/booking-confirmation/{booking_name}" if booking_name else "/portal"
	if token:
		target += f"?token={quote(token, safe='')}"

	frappe.local.flags.redirect_location = target
	frappe.local.response["type"] = "redirect"
	return context
