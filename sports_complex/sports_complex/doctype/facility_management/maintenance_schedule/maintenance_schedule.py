# Copyright (c) 2026, Your Company
# License: MIT

import frappe
from frappe.model.document import Document


class MaintenanceSchedule(Document):
	def validate(self):
		self.validate_times()
		self.validate_no_booking_conflict()

	def validate_times(self):
		if self.scheduled_start and self.scheduled_end:
			if self.scheduled_start >= self.scheduled_end:
				frappe.throw("Start Time must be earlier than End Time")

	def validate_no_booking_conflict(self):
		"""Prevent scheduling maintenance over an already-confirmed Facility Booking.

		Facility Booking is defined in the Booking Management module. Guard the
		check so Facility Management can be installed/tested standalone before
		Booking Management exists.
		"""
		if not frappe.db.exists("DocType", "Facility Booking"):
			return

		conflicts = frappe.db.sql(
			"""
			select name from `tabFacility Booking`
			where court = %(court)s
				and booking_date = %(scheduled_date)s
				and booking_status in ('Confirmed', 'Checked-In')
				and (start_time < %(scheduled_end)s and end_time > %(scheduled_start)s)
			""",
			{
				"court": self.court,
				"scheduled_date": self.scheduled_date,
				"scheduled_start": self.scheduled_start,
				"scheduled_end": self.scheduled_end,
			},
		)
		if conflicts:
			frappe.throw(
				f"Cannot schedule maintenance: Court {self.court} has an existing "
				f"confirmed booking in this time window ({conflicts[0][0]})"
			)

	def on_update(self):
		self.sync_court_status()

	def on_cancel(self):
		self.set_court_available()

	def sync_court_status(self):
		if self.status in ("Scheduled", "In Progress") and self.scheduled_date == frappe.utils.today():
			frappe.db.set_value("Court", self.court, "status", "Maintenance")
		elif self.status in ("Completed", "Cancelled"):
			self.set_court_available()

	def set_court_available(self):
		# Only flip back to Available if there isn't another active maintenance
		# window on this Court right now.
		other_active = frappe.db.exists(
			"Maintenance Schedule",
			{
				"court": self.court,
				"status": ("in", ["Scheduled", "In Progress"]),
				"name": ("!=", self.name),
				"scheduled_date": frappe.utils.today(),
			},
		)
		if not other_active:
			frappe.db.set_value("Court", self.court, "status", "Available")
