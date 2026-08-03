# Copyright (c) 2026, Your Company and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class BookingSchedule(Document):
	def validate(self):
		if self.slot_start and self.slot_end and self.slot_start >= self.slot_end:
			frappe.throw(_("Slot Start must be before Slot End"))
