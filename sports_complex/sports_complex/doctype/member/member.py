# Copyright (c) 2026, Your Company and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class Member(Document):
	def before_insert(self):
		if not self.customer:
			self.create_customer()

	def create_customer(self):
		"""Auto-create a 1:1 Customer record for this Member, per schema doc
		section 8. Booking/Membership/Tournament invoices bill against this
		Customer.
		"""
		customer = frappe.new_doc("Customer")
		customer.customer_name = self.member_name
		customer.customer_type = "Individual"
		if self.email:
			customer.email_id = self.email
		if self.phone:
			customer.mobile_no = self.phone
		customer.flags.ignore_permissions = True
		customer.insert()

		self.customer = customer.name
