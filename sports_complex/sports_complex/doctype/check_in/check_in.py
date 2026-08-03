# Copyright (c) 2026, Your Company and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class CheckIn(Document):
	def validate(self):
		booking_status = frappe.db.get_value("Facility Booking", self.facility_booking, "booking_status")
		if booking_status not in ("Confirmed",):
			frappe.throw(
				_("Facility Booking {0} must be Confirmed before check-in (current status: {1})").format(
					self.facility_booking, booking_status
				)
			)

	def on_submit(self):
		frappe.db.set_value("Facility Booking", self.facility_booking, "booking_status", "Checked-In")

	def on_cancel(self):
		frappe.db.set_value("Facility Booking", self.facility_booking, "booking_status", "Confirmed")
