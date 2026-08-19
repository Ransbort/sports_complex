# Copyright (c) 2026, Sports Complex and contributors
# For license information, please see license.txt
#
# Backend for the Trial Registration Cashier desk page - lets sports-complex
# front-of-house staff bill and collect the one-off Trial Registration Fee
# once a doctor has cleared a trialist (Trialist.medical_clearance_status ==
# "Cleared"), mirroring the Healthcare app's own Cashier Portal
# (healthcare/healthcare/page/cashier_portal/cashier_portal.py) but scoped to
# this single billing flow rather than a general-purpose multi-department
# till.
#
# Bill creation itself lives on the Trialist doctype
# (sports_complex.sports_complex.doctype.trialist.trialist.
# create_registration_invoice) so it can also be triggered from the Trialist
# form directly (see trialist.js's "Create Registration Bill" button) -
# this file only owns the billing queue, payment collection, and receipt
# printing, the same division of responsibility cashier_portal.py has
# relative to front_desk.py's own invoice creation.
#
# Path must match the JS calls exactly:
#   sports_complex.sports_complex.page.trial_registration_cashier.trial_registration_cashier.<method>

import frappe
from frappe import _
from frappe.utils import flt, nowdate
from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry


@frappe.whitelist()
def get_server_today():
	"""Same rationale as Healthcare's front_desk.get_server_today() /
	cashier_portal.get_server_today() - the cashier's browser can be in a
	different timezone than the site, so default any date fields here to
	the site's own nowdate() rather than the browser's local clock."""
	return nowdate()


@frappe.whitelist()
def get_trial_registration_fee():
	"""Read-only wrapper around Sports Complex Setup's configured fee, same
	reasoning as healthcare_integration.get_trial_appointment_type_for_client()
	- exposes this one non-sensitive value to Cashier-role users who don't
	necessarily have read access to Sports Complex Setup itself (payment
	gateway config, tax templates, etc. live there too)."""
	return flt(frappe.get_cached_doc("Sports Complex Setup").get("trial_registration_fee"))


@frappe.whitelist()
def get_billing_queue():
	"""Two buckets for the cashier's queue:
	  - awaiting_bill: medically cleared, no registration invoice raised yet
	    (registration_fee_status is "" or "Not Invoiced")
	  - awaiting_payment: invoice already raised (registration_fee_status ==
	    "Invoiced") but not yet paid - carries the linked Sales Invoice's
	    outstanding_amount so the cashier can see how much is left to
	    collect.
	Trialists whose fee is already "Paid" don't show up in either bucket -
	once billed and settled they drop off this queue, same as a fully-paid
	invoice disappearing from Healthcare's Cashier Portal.
	"""
	awaiting_bill = frappe.get_all(
		"Trialist",
		filters={
			"medical_clearance_status": "Cleared",
			"registration_fee_status": ["in", ["", "Not Invoiced"]],
		},
		fields=[
			"name", "full_name", "trial_batch", "sport",
			"medical_cleared_on", "customer", "mobile_number",
		],
		order_by="medical_cleared_on desc",
	)

	awaiting_payment = frappe.get_all(
		"Trialist",
		filters={"registration_fee_status": "Invoiced"},
		fields=[
			"name", "full_name", "trial_batch", "sport",
			"customer", "registration_invoice", "mobile_number",
		],
		order_by="modified desc",
	)

	invoice_names = [t["registration_invoice"] for t in awaiting_payment if t.get("registration_invoice")]
	invoices_by_name = {}
	if invoice_names:
		for row in frappe.get_all(
			"Sales Invoice",
			filters={"name": ["in", invoice_names]},
			fields=["name", "outstanding_amount", "grand_total", "currency", "status", "docstatus"],
		):
			invoices_by_name[row["name"]] = row

	for t in awaiting_payment:
		inv = invoices_by_name.get(t.get("registration_invoice")) or {}
		t["outstanding_amount"] = inv.get("outstanding_amount")
		t["grand_total"] = inv.get("grand_total")
		t["currency"] = inv.get("currency")
		t["invoice_status"] = inv.get("status")

	return {"awaiting_bill": awaiting_bill, "awaiting_payment": awaiting_payment}


@frappe.whitelist()
def get_invoice_items(invoice_name):
	"""Same shape as Healthcare's cashier_portal.get_invoice_items() - used
	to show the invoice line(s) before collecting payment."""
	doc = frappe.get_doc("Sales Invoice", invoice_name)
	items = []
	for item in doc.items:
		items.append({
			"item_code": item.item_code,
			"item_name": item.item_name,
			"description": item.description if item.description != item.item_name else None,
			"qty": item.qty,
			"rate": item.rate,
			"amount": item.amount,
		})
	return {
		"items": items,
		"outstanding_amount": doc.outstanding_amount,
		"grand_total": doc.grand_total,
		"currency": doc.currency,
	}


@frappe.whitelist()
def get_payment_methods():
	return frappe.get_all("Mode of Payment", filters={"enabled": 1}, fields=["name", "type"], order_by="name")


@frappe.whitelist()
def create_payment_entry(invoice_name, mode_of_payment, remarks=None, reference_no=None, reference_date=None):
	"""Collect payment against an already-raised registration invoice and
	flip the originating Trialist's registration_fee_status to "Paid".
	Mirrors cashier_portal.create_payment_entry() in the Healthcare app,
	plus the extra step of updating the Trialist (Healthcare's version has
	no such back-link to update - Patient billing status isn't tracked the
	same way)."""
	invoice = frappe.get_doc("Sales Invoice", invoice_name)
	if invoice.docstatus != 1:
		frappe.throw(_("Invoice {0} is not submitted yet.").format(invoice_name))
	if flt(invoice.outstanding_amount) <= 0:
		frappe.throw(_("Invoice {0} has nothing outstanding to collect.").format(invoice_name))

	pe = get_payment_entry("Sales Invoice", invoice_name)
	pe.mode_of_payment = mode_of_payment
	pe.paid_amount = invoice.outstanding_amount
	pe.received_amount = invoice.outstanding_amount

	if remarks:
		pe.remarks = remarks
	if reference_no:
		pe.reference_no = reference_no
	if reference_date:
		pe.reference_date = reference_date
	else:
		pe.reference_no = pe.reference_no or invoice_name
		pe.reference_date = pe.reference_date or nowdate()

	pe.insert(ignore_permissions=True)
	pe.submit()

	trialist_name = invoice.get("trialist")
	if trialist_name and frappe.db.exists("Trialist", trialist_name):
		frappe.db.set_value("Trialist", trialist_name, "registration_fee_status", "Paid")
		frappe.publish_realtime(
			event="trial_registration_fee_paid",
			message={
				"trialist": trialist_name,
				"invoice": invoice_name,
				"message": _("Registration fee paid for {0}").format(trialist_name),
			},
		)

	return {"status": "Success", "name": pe.name, "trialist": trialist_name}


@frappe.whitelist()
def get_print_content(doctype, docname):
	html = frappe.get_print(doctype, docname, print_format=None)
	return {"html": html}
