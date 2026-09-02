# Copyright (c) 2026, Sports Complex and contributors
# For license information, please see license.txt
#
# Unified Cashier - collapses what used to be two separate desk pages,
# Trial Registration Cashier (page/trial_registration_cashier) and the
# payment-collection half of Facility Check-In, into one till front-of-
# house staff work from for both kinds of outstanding payment: a trial
# registration fee, or a Facility Booking. Visual/structural language
# still traces back to Healthcare's own Cashier Portal (healthcare/
# healthcare/page/cashier_portal/cashier_portal.py) - same
# insert(ignore_permissions=True)+submit() Payment Entry pattern via
# get_payment_entry(), same get_print_content() receipt helper - just
# split here into two self-contained sections (Trial Registrations /
# Facility Bookings) rather than Healthcare's own department buckets,
# since those are this app's two actual billing flows.
#
# trial_registration_cashier.py's own functions are duplicated here
# rather than imported - see that page's own retirement note in
# trial_registration_cashier.js: it's now kept only as a thin redirect
# stub for anyone with an old bookmark, not as a dependency of this page,
# so this file doesn't take on a cross-page import just to avoid a few
# dozen duplicated lines.
#
# Facility Check-In used to have its own facility_checkin.mark_booking_paid()
# - a quick "staff attestation" shortcut on its "All Bookings" panel that
# flipped a booking's payment_status/booking_status straight to Paid/
# Confirmed with no Payment Entry ever created, leaving the linked Sales
# Invoice sitting Unpaid. It's been removed; this page is now the only
# place a Facility Booking's payment actually gets collected, and it
# always does so through a real, submitted Payment Entry.
#
# Path must match the JS calls exactly:
#   sports_complex.sports_complex.page.cashier.cashier.<method>

import frappe
from frappe import _
from frappe.utils import flt, nowdate
from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

CASHIER_ROLES = {"System Manager", "Sports Complex Manager", "Sports Complex Staff", "Cashier"}


def _is_cashier():
	return bool(set(frappe.get_roles()) & CASHIER_ROLES)


@frappe.whitelist()
def get_server_today():
	"""Same rationale as Healthcare's front_desk.get_server_today() - the
	cashier's browser can be in a different timezone than the site, so
	default any date fields here to the site's own nowdate() rather than
	the browser's local clock."""
	return nowdate()


@frappe.whitelist()
def get_payment_methods():
	return frappe.get_all("Mode of Payment", filters={"enabled": 1}, fields=["name", "type"], order_by="name")


@frappe.whitelist()
def get_print_content(doctype, docname):
	html = frappe.get_print(doctype, docname, print_format=None)
	return {"html": html}


# ---------------------------------------------------------------------
# Trial Registration section - behaviour ported unchanged from
# trial_registration_cashier.py; only the module path callers reach it
# through has moved.
# ---------------------------------------------------------------------

@frappe.whitelist()
def get_trial_registration_fee():
	"""Read-only wrapper around Sports Complex Setup's configured fee -
	exposes this one non-sensitive value to Cashier-role users who don't
	necessarily have read access to Sports Complex Setup itself (payment
	gateway config, tax templates, etc. live there too)."""
	return flt(frappe.get_cached_doc("Sports Complex Setup").get("trial_registration_fee"))


@frappe.whitelist()
def get_trial_billing_queue():
	"""Two buckets for the cashier's trial-registration queue:
	  - awaiting_bill: medically cleared, no registration invoice raised yet
	    (registration_fee_status is "" or "Not Invoiced")
	  - awaiting_payment: invoice already raised (registration_fee_status ==
	    "Invoiced") but not yet paid - carries the linked Sales Invoice's
	    outstanding_amount so the cashier can see how much is left to
	    collect.
	Trialists whose fee is already "Paid" don't show up in either bucket.
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
def create_trial_payment_entry(invoice_name, mode_of_payment, remarks=None, reference_no=None, reference_date=None):
	"""Collect payment against an already-raised registration invoice and
	flip the originating Trialist's registration_fee_status to "Paid".
	Adds an explicit _is_cashier() gate the original trial_registration_
	cashier.create_payment_entry() didn't have (it relied purely on the
	Page's own role restriction) - worth tightening here since this
	creates a real accounting entry, not just worth carrying the old gap
	forward into the merged page.
	"""
	if not _is_cashier():
		frappe.throw(_("Not permitted to collect payment"), frappe.PermissionError)

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


# ---------------------------------------------------------------------
# Facility Bookings section
# ---------------------------------------------------------------------

@frappe.whitelist()
def get_facility_pending_payments(facility=None, date=None, customer=None):
	"""Submitted Facility Bookings still owed money - the queue the
	Facility Bookings tab works through. A deliberately standalone query
	rather than reusing facility_checkin's own _booking_filters() helper -
	that one also branches on a "jump to booking" filter this tab has no
	equivalent field for, and importing it just for the two filters this
	does use isn't worth the cross-page dependency.
	"""
	filters = {
		"docstatus": 1,
		"payment_status": ["!=", "Paid"],
		"booking_status": ["not in", ["Cancelled"]],
	}
	if facility:
		filters["court"] = facility
	if date:
		filters["booking_date"] = date

	or_filters = None
	if customer:
		like = f"%{customer}%"
		matching_customer_ids = frappe.get_all(
			"Customer", filters={"customer_name": ["like", like]}, pluck="name"
		) or [""]
		or_filters = [
			["customer", "in", matching_customer_ids],
			["customer", "like", like],
			["email", "like", like],
			["phone", "like", like],
		]

	bookings = frappe.get_all(
		"Facility Booking",
		filters=filters,
		or_filters=or_filters,
		fields=[
			"name", "customer", "court", "booking_date", "start_time", "end_time",
			"total_amount", "booking_status", "payment_status", "sales_invoice",
		],
		order_by="booking_date asc, start_time asc",
	)

	facility_names = list({b.court for b in bookings if b.court})
	facility_labels = dict(frappe.get_all(
		"Sports Facility",
		filters={"name": ["in", facility_names]},
		fields=["name", "facility_name"],
		as_list=True,
	)) if facility_names else {}

	invoice_names = [b.sales_invoice for b in bookings if b.sales_invoice]
	outstanding_by_invoice = dict(frappe.get_all(
		"Sales Invoice",
		filters={"name": ["in", invoice_names]},
		fields=["name", "outstanding_amount"],
		as_list=True,
	)) if invoice_names else {}

	for b in bookings:
		b["facility_name"] = facility_labels.get(b.court) or b.court
		b["booking_date"] = str(b.booking_date) if b.booking_date else None
		b["start_time"] = str(b.start_time) if b.start_time else None
		b["end_time"] = str(b.end_time) if b.end_time else None
		b["outstanding_amount"] = (
			flt(outstanding_by_invoice.get(b.sales_invoice)) if b.sales_invoice else flt(b.total_amount)
		)

	return bookings


@frappe.whitelist()
def create_facility_payment_entry(
	facility_booking, mode_of_payment, paid_amount=None, remarks=None, reference_no=None, reference_date=None
):
	"""Collect payment against a Facility Booking's Sales Invoice and, once
	it's fully settled, bring the booking itself in line via Facility
	Booking.mark_paid_and_confirm() - the same method Paystack's own
	webhook calls once it confirms an online payment (see
	utils/paystack_hooks.py), just reached here after a real Payment
	Entry this function created and submitted instead of a webhook. A
	partial payment (paid_amount less than the full outstanding balance)
	leaves the booking's payment_status at
	"Partially Paid" and its booking_status untouched instead - a
	Payment-Pending booking stays Payment Pending until it's paid off in
	full, matching what "Require Payment Before Booking Confirmation" is
	meant to enforce.
	"""
	if not _is_cashier():
		frappe.throw(_("Not permitted to collect payment"), frappe.PermissionError)

	booking = frappe.get_doc("Facility Booking", facility_booking)
	if not booking.sales_invoice:
		frappe.throw(_("Booking {0} has no linked Sales Invoice to pay against").format(facility_booking))

	invoice = frappe.get_doc("Sales Invoice", booking.sales_invoice)
	if invoice.docstatus != 1:
		frappe.throw(_("Invoice {0} is not submitted yet.").format(invoice.name))
	if flt(invoice.outstanding_amount) <= 0:
		frappe.throw(_("Invoice {0} has nothing outstanding to collect.").format(invoice.name))

	amount = flt(paid_amount) if paid_amount else flt(invoice.outstanding_amount)
	if amount <= 0 or amount > flt(invoice.outstanding_amount) + 0.01:
		frappe.throw(
			_("Payment amount must be between 0 and the outstanding balance ({0})").format(invoice.outstanding_amount)
		)

	pe = get_payment_entry("Sales Invoice", invoice.name)
	pe.mode_of_payment = mode_of_payment
	pe.paid_amount = amount
	pe.received_amount = amount
	# get_payment_entry() pre-allocates the invoice's full outstanding
	# amount against itself in the one reference row it creates - re-point
	# that at whatever was actually collected for a partial payment, so
	# Payment Entry's own validate() doesn't try to allocate more than
	# paid_amount and leave a phantom unallocated balance.
	if pe.references:
		pe.references[0].allocated_amount = amount

	if remarks:
		pe.remarks = remarks
	if reference_no:
		pe.reference_no = reference_no
	if reference_date:
		pe.reference_date = reference_date
	else:
		pe.reference_no = pe.reference_no or facility_booking
		pe.reference_date = pe.reference_date or nowdate()

	pe.insert(ignore_permissions=True)
	pe.submit()

	invoice.reload()
	if flt(invoice.outstanding_amount) <= 0:
		booking.mark_paid_and_confirm()
	else:
		booking.db_set("payment_status", "Partially Paid")

	return {
		"status": "Success",
		"name": pe.name,
		"booking_status": booking.booking_status,
		"payment_status": booking.payment_status,
		"outstanding_amount": invoice.outstanding_amount,
	}
