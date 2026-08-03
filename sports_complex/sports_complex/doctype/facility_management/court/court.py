# Copyright (c) 2026, Your Company
# License: MIT

import frappe
from frappe.model.document import Document


class Court(Document):
	def get_effective_hourly_rate(self):
		if self.hourly_rate:
			return self.hourly_rate
		facility = frappe.get_cached_doc("Sports Facility", self.sports_facility)
		return facility.get_effective_hourly_rate()

	def is_under_maintenance(self, check_date, start_time, end_time):
		"""Returns True if this Court has an overlapping Maintenance Schedule entry.

		Used by Facility Booking (Booking Management module) before confirming a slot.
		"""
		overlaps = frappe.db.sql(
			"""
			select name from `tabMaintenance Schedule`
			where court = %(court)s
				and scheduled_date = %(check_date)s
				and status in ('Scheduled', 'In Progress')
				and (
					(scheduled_start < %(end_time)s and scheduled_end > %(start_time)s)
				)
			""",
			{
				"court": self.name,
				"check_date": check_date,
				"start_time": start_time,
				"end_time": end_time,
			},
		)
		return bool(overlaps)
