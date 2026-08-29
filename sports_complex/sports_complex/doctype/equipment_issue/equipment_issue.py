# Copyright (c) 2026, Sports Complex and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from sports_complex.utils import cancel_linked_invoice, get_member_customer, make_linked_sales_invoice


class EquipmentIssue(Document):
	def validate(self):
		equipment_status = frappe.db.get_value("Equipment", self.equipment, "status")
		if self.docstatus == 0 and equipment_status not in ("Available",):
			frappe.throw(
				_("Equipment {0} is not Available (current status: {1}).").format(
					self.equipment, equipment_status
				)
			)

	def on_submit(self):
		frappe.db.set_value("Equipment", self.equipment, "status", "Issued")
		self.create_rental_invoice()

	def on_cancel(self):
		frappe.db.set_value("Equipment", self.equipment, "status", "Available")
		cancel_linked_invoice(self.sales_invoice)

	def create_rental_invoice(self):
		if not self.rental_fee:
			return

		customer = self.get_customer()
		if not customer:
			frappe.msgprint(_("No linked Customer found - skipping invoice creation."), alert=True)
			return

		si = make_linked_sales_invoice(
			customer=customer,
			item_code="Equipment Rental Fee",
			item_group="Equipment Rental",
			amount=self.rental_fee,
			link_fieldname="equipment_issue",
			link_docname=self.name,
			description=f"Rental - {self.equipment}",
		)
		si.submit()
		self.db_set("sales_invoice", si.name)

	def get_customer(self):
		if self.issued_to_type == "Member" and self.issued_to_member:
			return get_member_customer(self.issued_to_member)
		# Coach / Team issues typically go on a house account or deposit-only -
		# extend here if coaches/teams should also be billed as Customers.
		return None
