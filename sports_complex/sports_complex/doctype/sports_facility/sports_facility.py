# Copyright (c) 2026, Your Company
# License: MIT

import frappe
from frappe.model.document import Document

from sports_complex.utils.attachments import make_attached_image_public


class SportsFacility(Document):
	def validate(self):
		if not self.hourly_rate and self.facility_type:
			default_rate = frappe.db.get_value("Facility Type", self.facility_type, "default_hourly_rate")
			if default_rate:
				self.hourly_rate = default_rate
		make_attached_image_public(self, "image")

	def get_effective_hourly_rate(self):
		"""Used by Facility Booking when this facility has no rate override
		of its own."""
		if self.hourly_rate:
			return self.hourly_rate
		return frappe.db.get_value("Facility Type", self.facility_type, "default_hourly_rate") or 0

	def is_under_maintenance(self, check_date, start_time, end_time):
		"""Returns True if this facility has an overlapping Maintenance
		Schedule entry.

		Moved here from the old Court doctype - Sports Facility is now the
		sole bookable unit (a facility used to have one or more Court
		"units" under it; in practice every facility only ever had exactly
		one, so that extra layer was pure overhead). Maintenance Schedule's
		own `court` field still literally reads "court" (renaming an
		existing column with live data is riskier than it's worth), but it
		now points at Sports Facility - see the migration patch in
		sports_complex/patches/remove_court_doctype.py.
		"""
		overlaps = frappe.db.sql(
			"""
			select name from `tabMaintenance Schedule`
			where court = %(facility)s
				and scheduled_date = %(check_date)s
				and status in ('Scheduled', 'In Progress')
				and (scheduled_start < %(end_time)s and scheduled_end > %(start_time)s)
			""",
			{
				"facility": self.name,
				"check_date": check_date,
				"start_time": start_time,
				"end_time": end_time,
			},
		)
		return bool(overlaps)

	def on_update(self):
		self.sync_time_slots()

	def sync_time_slots(self):
		"""Full mirror, not a create-or-update: every Booking Schedule row
		for this facility is replaced with exactly what's in the Time
		Slots table, on every save. Safe to do wholesale because nothing
		else in the app links to a Booking Schedule row by name -
		get_available_slots() only ever reads them by (facility,
		day_of_week).
		"""
		frappe.db.delete("Booking Schedule", {"court": self.name})

		for row in self.time_slots:
			frappe.get_doc(
				{
					"doctype": "Booking Schedule",
					"court": self.name,
					"day_of_week": row.day_of_week,
					"slot_start": row.slot_start,
					"slot_end": row.slot_end,
					"slot_duration": row.slot_duration,
					"is_active": row.is_active,
				}
			).insert(ignore_permissions=True)
