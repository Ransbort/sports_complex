# Copyright (c) 2026, Sports Complex and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from sports_complex.sports_complex.utils import get_member_customer, make_linked_sales_invoice


class EquipmentReturn(Document):
	def validate(self):
		existing = frappe.db.get_value(
			"Equipment Return",
			{"equipment_issue": self.equipment_issue, "name": ["!=", self.name or ""], "docstatus": ["!=", 2]},
			"name",
		)
		if existing:
			frappe.throw(_("Equipment Issue {0} already has a Return recorded.").format(self.equipment_issue))

	def on_submit(self):
		issue = frappe.get_doc("Equipment Issue", self.equipment_issue)
		frappe.db.set_value("Equipment", issue.equipment, "status", "Available")
		frappe.db.set_value("Equipment", issue.equipment, "condition", self.condition_at_return)
		frappe.db.set_value("Equipment Issue", issue.name, "status", "Returned")

		if self.damage_charge:
			self.create_damage_invoice(issue)

	def create_damage_invoice(self, issue):
		customer = None
		if issue.issued_to_type == "Member" and issue.issued_to_member:
			customer = get_member_customer(issue.issued_to_member)

		if not customer:
			frappe.msgprint(
				_("No linked Customer found for damage charge - please invoice manually."), alert=True
			)
			return

		si = make_linked_sales_invoice(
			customer=customer,
			item_code="Equipment Damage Charge",
			item_group="Equipment Rental",
			amount=self.damage_charge,
			link_fieldname="equipment_return",
			link_docname=self.name,
			description=f"Damage charge - {issue.equipment} ({self.equipment_issue})",
		)
		self.db_set("sales_invoice", si.name)
