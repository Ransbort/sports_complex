# Copyright (c) 2026, Your Company and contributors
# For license information, please see license.txt

"""Adds Facility Booking to the Customer form's own "Connections" dashboard
(the same section that already shows a Customer's Sales Orders, Invoices,
etc.) instead of a bespoke "this customer's bookings" table on the Facility
Booking form itself - see facility_booking.js's "View All Bookings" button
for the matching entry point from the booking side.

Wired via hooks.py's override_doctype_dashboards, which Frappe calls with
whatever Customer's own dashboard already built (ERPNext's own connections
for Sales Order/Sales Invoice/etc. included) so this only needs to append
its own group, not reconstruct the whole thing.
"""

from frappe import _


def get_data(data):
	data.setdefault("transactions", [])
	data["transactions"].append(
		{
			"label": _("Sports Complex"),
			"items": ["Facility Booking"],
		}
	)
	# Facility Booking links back to Customer via a field literally named
	# "customer" - the same default fieldname Customer's base dashboard
	# already assumes for every other linked doctype, so no non_standard_
	# fieldnames entry is needed here.
	return data
