# Copyright (c) 2026, Sports Complex and contributors
# For license information, please see license.txt

"""Called from the Sales Invoice on_payment_authorized doc_event (wired in
hooks.py) once frappe_paystack's webhook confirms payment. Walks the
back-link custom fields added in fixtures/custom_field.json and updates the
matching status field on whichever source doc created the invoice."""

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
		if status_field in frappe.get_meta(source_doctype).get_valid_columns():
			frappe.db.set_value(source_doctype, source_name, status_field, paid_value)
			frappe.db.commit()
		break
