# Copyright (c) 2026, Sports Complex and contributors
# For license information, please see license.txt

"""Shared helper for the "every payable doc creates a Sales Invoice" pattern
described in section 0 / section 11 of the schema. Keep this in one place so
Facility Booking, Membership, Tournament Registration, Equipment Issue/Return
and Training Session all reconcile with frappe_paystack the same way.
"""

import frappe
from frappe import _
from frappe.utils import nowdate


def get_or_create_item(item_code, item_group, rate=None):
	"""Ensure a billable Item exists for a given source (facility usage,
	tournament entry fee, equipment rental, etc.) so we don't hand
	frappe_paystack/ERPNext an invoice line with no Item."""
	if frappe.db.exists("Item", item_code):
		return item_code

	item = frappe.new_doc("Item")
	item.item_code = item_code
	item.item_name = item_code
	item.item_group = item_group
	item.is_stock_item = 0
	item.is_sales_item = 1
	item.stock_uom = "Nos"
	if rate:
		item.standard_rate = rate
	item.insert(ignore_permissions=True)
	return item.name


def get_default_company():
	"""Sports Complex Setup's Default Company, falling back to the site's
	global default Company if not configured."""
	company = frappe.db.get_single_value("Sports Complex Setup", "default_company")
	return company or frappe.defaults.get_global_default("company")


def get_account(parentfield, company):
	"""Look up a Company-specific account row from Sports Complex Setup's
	Income Account / Receivable Account child tables (both use the core
	Party Account child doctype: company + account + advance_account) -
	same lookup shape as healthcare.healthcare.doctype.healthcare_settings.
	healthcare_settings.get_account().
	"""
	if not company:
		return None
	return frappe.db.get_value(
		"Party Account",
		{"parenttype": "Sports Complex Setup", "parentfield": parentfield, "company": company},
		"account",
	)


def get_receivable_account(company=None):
	"""Sports Complex Setup > Default Accounts > Receivable Account for
	`company` (or the default Company if not given), falling back to that
	Company's own default receivable account if nothing is configured."""
	company = company or get_default_company()
	return get_account("receivable_account", company) or (
		company and frappe.get_cached_value("Company", company, "default_receivable_account")
	)


def get_income_account(company=None):
	"""Sports Complex Setup > Default Accounts > Income Account for
	`company` (or the default Company if not given), falling back to that
	Company's own default income account if nothing is configured."""
	company = company or get_default_company()
	return get_account("income_account", company) or (
		company and frappe.get_cached_value("Company", company, "default_income_account")
	)


def make_linked_sales_invoice(
	customer,
	item_code,
	item_group,
	amount,
	link_fieldname,
	link_docname,
	description=None,
	qty=1,
):
	"""Create a draft Sales Invoice against `customer` for `amount`, stamping
	the custom back-link field (e.g. tournament_registration, equipment_issue)
	added to Sales Invoice per section 6, and return it. Does NOT submit -
	each caller decides when to submit (see Facility Booking and Trialist for
	the established "submit right after this returns" pattern, required both
	to post to the ledger and because frappe_paystack refuses to attach a
	payment link/log to a draft invoice - see PaystackPaymentLog.validate_record()).

	The frappe_paystack fork picks up the Paystack "Pay Now" button from the
	standard Sales Invoice form - nothing else needs to be done here.
	"""
	if not customer:
		frappe.throw(_("Cannot create a Sales Invoice without a Customer."))

	get_or_create_item(item_code, item_group, rate=amount)

	company = get_default_company()

	si = frappe.new_doc("Sales Invoice")
	si.customer = customer
	si.posting_date = nowdate()
	if company:
		si.company = company
		receivable_account = get_receivable_account(company)
		if receivable_account:
			si.debit_to = receivable_account

	item_row = {
		"item_code": item_code,
		"item_name": item_code,
		"description": description or item_code,
		"qty": qty,
		"rate": amount,
	}
	income_account = get_income_account(company)
	if income_account:
		item_row["income_account"] = income_account
	si.append("items", item_row)

	# custom back-link field from the Sales Invoice fixtures in section 6
	if link_fieldname:
		si.set(link_fieldname, link_docname)

	si.insert(ignore_permissions=True)
	return si


def cancel_linked_invoice(sales_invoice):
	"""Cancel a linked Sales Invoice, if any, when the parent doc (Membership,
	Equipment Issue, Tournament Registration, ...) is cancelled - otherwise
	cancelling the parent would leave an orphaned invoice still open on the
	books for a service that's no longer being rendered. No-op if there's no
	invoice, or it's already a draft/cancelled.
	"""
	if not sales_invoice or not frappe.db.exists("Sales Invoice", sales_invoice):
		return

	si = frappe.get_doc("Sales Invoice", sales_invoice)
	if si.docstatus != 1:
		return

	try:
		si.flags.ignore_permissions = True
		si.cancel()
	except Exception as e:
		frappe.throw(
			_(
				"Cannot cancel: linked Sales Invoice {0} could not be cancelled "
				"automatically ({1}). If it has been paid, reverse/cancel that "
				"payment first, then cancel this document again."
			).format(si.name, str(e))
		)


def get_member_customer(member):
	"""Members are 1:1 with Customer (section 3/8) - resolve the Customer
	behind a Member link."""
	if not member:
		return None
	return frappe.db.get_value("Member", member, "customer")
