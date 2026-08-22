# Copyright (c) 2026, Sports Complex and contributors
# For license information, please see license.txt

"""Called from the Sales Invoice on_payment_authorized doc_event (wired in
hooks.py) once frappe_paystack's webhook confirms payment. Walks the
back-link custom fields added in fixtures/custom_field.json and updates the
matching status field on whichever source doc created the invoice.

hooks.py's doc_events entry for this pointed at
"sports_complex.sports_complex.utils.paystack_hooks.on_payment_authorized"
for a while - one ".sports_complex" too many; this module is
sports_complex.utils.paystack_hooks, not sports_complex.sports_complex.
utils.paystack_hooks. Fixed back to the path that actually resolves here.

Separately: on_payment_authorized isn't a Frappe/ERPNext event that fires
on its own - something has to explicitly run_method() it, the way
ERPNext's own Payment Request flow does after a gateway confirms payment.
frappe_paystack's own Paystack Payment Log.on_update() (in the
frappe_paystack app) never calls it - it just updates the log itself and,
once the invoice is fully settled, creates/submits a Payment Entry
directly. So this hook was very likely dead code even before the path
typo above. on_payment_log_update() below is the entry point that
actually fires - see hooks.py's doc_events.
"""

import frappe

# fieldname on Sales Invoice -> (source doctype, status fieldname, paid value)
SOURCE_MAP = {
	"facility_booking": ("Facility Booking", "payment_status", "Paid"),
	"membership": ("Membership", "status", "Active"),
	"membership_renewal": ("Membership Renewal", "status", "Completed"),
	"tournament_registration": ("Tournament Registration", "status", "Confirmed"),
	"training_session": ("Training Session", "payment_status", "Paid"),
	"equipment_issue": ("Equipment Issue", "payment_status", "Paid"),
	"equipment_return": ("Equipment Return", "payment_status", "Paid"),
	# Trial Registration Fee invoices - see Trialist.create_registration_invoice()
	# in doctype/trialist/trialist.py. Covers the case where a trialist's bill
	# gets paid via frappe_paystack's own "Pay Now" button on the Sales
	# Invoice directly, rather than through the Trial Registration Cashier
	# page's manual Payment Entry flow (which sets this itself - see
	# create_payment_entry() in page/trial_registration_cashier/
	# trial_registration_cashier.py).
	"trialist": ("Trialist", "registration_fee_status", "Paid"),
}


def on_payment_authorized(doc, method=None):
	"""doc: Sales Invoice"""
	for fieldname, (source_doctype, status_field, paid_value) in SOURCE_MAP.items():
		source_name = doc.get(fieldname)
		if not source_name:
			continue
		if not frappe.db.exists(source_doctype, source_name):
			continue
		if source_doctype == "Facility Booking":
			# Facility Booking also gates a booking_status transition
			# (Payment Pending -> Confirmed) behind payment confirmation,
			# not just the payment_status field every other source doc
			# here uses a plain db.set_value for - see
			# FacilityBooking.mark_paid_and_confirm(), which is
			# idempotent the same way this loop already assumes
			# db.set_value is (safe to run more than once for one
			# payment).
			frappe.get_doc(source_doctype, source_name).mark_paid_and_confirm()
		elif status_field in frappe.get_meta(source_doctype).get_valid_columns():
			frappe.db.set_value(source_doctype, source_name, status_field, paid_value)
			frappe.db.commit()
		break


def on_payment_log_update(doc, method=None):
	"""doc: Paystack Payment Log. The hook that actually fires in
	practice - see the module docstring for why Sales Invoice.
	on_payment_authorized above most likely never does with this
	frappe_paystack integration. Delegates to on_payment_authorized()
	once the linked Sales Invoice is loaded, so both entry points run
	the exact same SOURCE_MAP logic rather than maintaining it twice.
	"""
	if doc.status != "Processed":
		return
	if doc.linked_doctype != "Sales Invoice" or not doc.linked_docname:
		return
	if not frappe.db.exists("Sales Invoice", doc.linked_docname):
		return
	on_payment_authorized(frappe.get_doc("Sales Invoice", doc.linked_docname))
