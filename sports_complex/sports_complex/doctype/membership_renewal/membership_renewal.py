# Copyright (c) 2026, Your Company and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_months


class MembershipRenewal(Document):
	def validate(self):
		self.calculate_new_end_date()

	def calculate_new_end_date(self):
		if not self.membership:
			return

		membership_plan, previous_end_date = frappe.db.get_value(
			"Membership", self.membership, ["membership_plan", "end_date"]
		)
		self.previous_end_date = previous_end_date

		duration_months = frappe.db.get_value("Membership Plan", membership_plan, "duration_months")
		if duration_months and previous_end_date:
			self.new_end_date = add_months(previous_end_date, duration_months)

	def on_submit(self):
		self.create_sales_invoice()
		self.db_update()

		frappe.db.set_value("Membership", self.membership, "end_date", self.new_end_date)
		frappe.db.set_value("Membership", self.membership, "status", "Active")

	def create_sales_invoice(self):
		"""Bill the renewal amount, using the same Item as the original
		Membership Plan (see Membership.create_sales_invoice for the
		Item-naming assumption).
		"""
		if self.sales_invoice:
			return

		membership_plan, member = frappe.db.get_value(
			"Membership", self.membership, ["membership_plan", "member"]
		)

		if not frappe.db.exists("Item", membership_plan):
			frappe.throw(
				_("No Item found named {0}. Create a sellable Item matching the Membership Plan name.").format(
					membership_plan
				)
			)

		customer = frappe.db.get_value("Member", member, "customer")
		if not customer:
			frappe.throw(_("Member {0} has no linked Customer").format(member))

		si = frappe.new_doc("Sales Invoice")
		si.customer = customer
		si.membership_renewal = self.name
		si.append(
			"items",
			{
				"item_code": membership_plan,
				"qty": 1,
				"rate": self.amount,
			},
		)
		si.flags.ignore_permissions = True
		si.insert()

		self.sales_invoice = si.name
