# Copyright (c) 2026, Your Company and contributors
# For license information, please see license.txt

"""Flow Paystack payment confirmation back onto whichever source
doctype created the Sales Invoice being paid. Facility Booking is wired
up today (see FacilityBooking.mark_paid_and_confirm()); Membership,
Tournament Registration, Training Session and Equipment Issue/Return
already have their own `*_registration`/etc. Custom Field on Sales
Invoice (see the app's setup.py / fixtures/custom_field.json) but
aren't wired to a confirmation handler here yet.

Two entry points are registered in hooks.py, and both end up here:

- Paystack Payment Log.on_update - this is the one that actually fires
  in practice. frappe_paystack's verify_transaction() (the synchronous
  fallback the checkout page's Paystack popup calls immediately after
  a charge completes client-side) and its webhook handler both just do
  `log.save(...)` once a payment settles - neither creates a Payment
  Entry or calls any Sales Invoice-level hook. So:

- Sales Invoice.on_payment_authorized - this was already referenced in
  this app's hooks.py before this module existed, pointing at
  `sports_complex.sports_complex.utils.paystack_hooks.on_payment_authorized`
  in a `utils` package that didn't exist anywhere in the app - an
  import error waiting to happen the first time (if ever) that event
  actually fired, since Frappe resolves a doc_event's target lazily on
  first fire rather than at app load. Implemented here as a safe
  fallback in case a future Payment Entry-based flow (or a different
  frappe_paystack fork) does fire it, but as things stand today it's
  Paystack Payment Log.on_update doing the real work.
"""

import frappe


def on_payment_log_update(doc, method=None):
	"""doc is a Paystack Payment Log."""
	if doc.status != "Processed":
		return
	if doc.linked_doctype != "Sales Invoice" or not doc.linked_docname:
		return
	_confirm_facility_booking_for_invoice(doc.linked_docname)


def on_payment_authorized(doc, method=None):
	"""doc is a Sales Invoice here, not a Paystack Payment Log - see the
	module docstring for why this most likely never actually fires with
	frappe_paystack as it stands.
	"""
	_confirm_facility_booking_for_invoice(doc.name)


def _confirm_facility_booking_for_invoice(sales_invoice):
	booking_name = frappe.db.get_value("Sales Invoice", sales_invoice, "facility_booking")
	if not booking_name:
		return
	frappe.get_doc("Facility Booking", booking_name).mark_paid_and_confirm()
