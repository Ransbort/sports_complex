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
	"""Create a submitted-ready (draft) Sales Invoice against `customer` for
	`amount`, stamping the custom back-link field (e.g. tournament_registration,
	equipment_issue) added to Sales Invoice per section 6, and return it.

	The frappe_paystack fork picks up the Paystack "Pay Now" button from the
	standard Sales Invoice form - nothing else needs to be done here.
	"""
	if not customer:
		frappe.throw(_("Cannot create a Sales Invoice without a Customer."))

	get_or_create_item(item_code, item_group, rate=amount)

	si = frappe.new_doc("Sales Invoice")
	si.customer = customer
	si.posting_date = nowdate()
	si.append(
		"items",
		{
			"item_code": item_code,
			"item_name": item_code,
			"description": description or item_code,
			"qty": qty,
			"rate": amount,
		},
	)
	# custom back-link field from the Sales Invoice fixtures in section 6
	if link_fieldname:
		si.set(link_fieldname, link_docname)

	si.insert(ignore_permissions=True)
	return si


def get_member_customer(member):
	"""Members are 1:1 with Customer (section 3/8) - resolve the Customer
	behind a Member link."""
	if not member:
		return None
	return frappe.db.get_value("Member", member, "customer")
