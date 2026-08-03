# Copyright (c) 2026, Your Company
# License: MIT

import frappe
from frappe.model.document import Document


class SportsFacility(Document):
	def validate(self):
		if not self.hourly_rate and self.facility_type:
			default_rate = frappe.db.get_value("Facility Type", self.facility_type, "default_hourly_rate")
			if default_rate:
				self.hourly_rate = default_rate

	def get_effective_hourly_rate(self):
		"""Used by Court / Facility Booking when a Court doesn't have its own override."""
		if self.hourly_rate:
			return self.hourly_rate
		return frappe.db.get_value("Facility Type", self.facility_type, "default_hourly_rate") or 0
