# Copyright (c) 2026, Your Company and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_months

from sports_complex.utils.invoicing import (
	cancel_linked_invoice,
	get_default_company,
	get_income_account,
	get_receivable_account,
)


class Membership(Document):
	def validate(self):
		self.calculate_end_date()

	def calculate_end_date(self):
		if self.start_date and self.membership_plan:
			duration_months = frappe.db.get_value("Membership Plan", self.membership_plan, "duration_months")
			if duration_months:
				self.end_date = add_months(self.start_date, duration_months)

	def on_submit(self):
		self.create_sales_invoice()
		self.db_update()

		frappe.db.set_value("Member", self.member, "membership_status", "Active")

	def on_cancel(self):
		frappe.db.set_value("Membership", self.name, "status", "Cancelled")
		cancel_linked_invoice(self.sales_invoice)

	def create_sales_invoice(self):
		"""Bill the Membership Plan's price.

		NOTE: assumes a sellable Item exists with the same name as the
		Membership Plan (e.g. an Item literally called "Gold Monthly" if
		that's your plan name). Adjust if you'd rather bill against one
		shared "Membership Fee" Item instead.
		"""
		if self.sales_invoice:
			return

		if not frappe.db.exists("Item", self.membership_plan):
			frappe.throw(
				_(
					"No Item found named {0}. Create a sellable Item matching the "
					"Membership Plan name before confirming memberships."
				).format(self.membership_plan)
			)

		customer = frappe.db.get_value("Member", self.member, "customer")
		if not customer:
			frappe.throw(_("Member {0} has no linked Customer").format(self.member))

		price = frappe.db.get_value("Membership Plan", self.membership_plan, "price")
		company = get_default_company()

		si = frappe.new_doc("Sales Invoice")
		si.customer = customer
		si.membership = self.name
		if company:
			si.company = company
			receivable_account = get_receivable_account(company)
			if receivable_account:
				si.debit_to = receivable_account

		item_row = {
			"item_code": self.membership_plan,
			"qty": 1,
			"rate": price,
		}
		income_account = get_income_account(company)
		if income_account:
			item_row["income_account"] = income_account
		si.append("items", item_row)

		si.flags.ignore_permissions = True
		si.insert()
		si.submit()

		self.sales_invoice = si.name
