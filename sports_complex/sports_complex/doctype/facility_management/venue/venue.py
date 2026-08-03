# Copyright (c) 2026, Your Company
# License: MIT

import frappe
from frappe.model.document import Document


class Venue(Document):
	def validate(self):
		if self.operating_hours_from and self.operating_hours_to:
			if self.operating_hours_from >= self.operating_hours_to:
				frappe.throw("Operating Hours From must be earlier than Operating Hours To")
