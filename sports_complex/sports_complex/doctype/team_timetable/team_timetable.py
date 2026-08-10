# Copyright (c) 2026, Pep Sports Limited and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_time


class TeamTimetable(Document):
	def validate(self):
		self.validate_time_range()
		self.validate_no_overlap()

	def validate_time_range(self):
		if self.start_time and self.end_time and get_time(self.end_time) <= get_time(self.start_time):
			frappe.throw(_("End Time must be after Start Time."))

	def validate_no_overlap(self):
		"""Flag (rather than silently allow) two slots for the same team
		on the same day that overlap in time — a simple sanity check
		since this is manually entered, not derived from a calendar."""

		if not (self.team and self.day_of_week and self.start_time and self.end_time):
			return

		existing = frappe.get_all(
			"Team Timetable",
			filters={
				"team": self.team,
				"day_of_week": self.day_of_week,
				"name": ["!=", self.name or ""],
			},
			fields=["name", "start_time", "end_time"],
		)

		new_start, new_end = get_time(self.start_time), get_time(self.end_time)

		for row in existing:
			existing_start, existing_end = get_time(row.start_time), get_time(row.end_time)
			if new_start < existing_end and existing_start < new_end:
				frappe.throw(
					_("This overlaps with an existing {0} slot ({1} – {2}) for this team.").format(
						row.name, row.start_time, row.end_time
					)
				)
