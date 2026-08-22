# Copyright (c) 2026, Your Company and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_time


class BookingSchedule(Document):
	def validate(self):
		# get_time() normalizes both sides to a real datetime.time before
		# comparing - same fix, same reason, as FacilityBooking.
		# validate_times() and Sports Facility Time Slot.validate(): a
		# plain string/timedelta >= comparison here is lexicographic, not
		# a time comparison, so e.g. "8:00:00" >= "16:00:00" is True and a
		# perfectly valid slot gets rejected. Booking Schedule rows are
		# rewritten wholesale from Sports Facility's Time Slots table on
		# every save (see Sports Facility.sync_time_slots()), which is
		# exactly where this was surfacing.
		if self.slot_start and self.slot_end and get_time(self.slot_start) >= get_time(self.slot_end):
			frappe.throw(_("Slot Start must be before Slot End"))
