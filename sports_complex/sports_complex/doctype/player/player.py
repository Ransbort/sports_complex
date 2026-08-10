# Copyright (c) 2026, Pep Sports Limited and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class Player(Document):
	def validate(self):
		self.set_full_name()

	def set_full_name(self):
		self.full_name = " ".join(
			part for part in [self.first_name, self.last_name] if part
		).strip()
