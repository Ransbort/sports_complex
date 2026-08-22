# Copyright (c) 2026, Sports Complex and contributors
# For license information, please see license.txt

from datetime import datetime

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_time


class SportsFacilityTimeSlot(Document):
	def validate(self):
		"""Same spirit as Healthcare's Practitioner Schedule time slot
		(Healthcare Schedule Time Slot.validate() via Practitioner
		Schedule.validate()), which checks its from_time/to_time/duration/
		maximum_appointments are internally consistent before the schedule
		is saved. We don't have a maximum_appointments field - Facility
		Booking generates bookable slots straight from slot_duration - so
		the equivalent invariant here is: the window is real (start before
		end) and the duration actually fits inside it at least once.
		Without this, a bad row (duration longer than the window, or a
		flipped start/end) saved silently and only broke later, at
		booking time, in a way that was confusing to track back to its
		source - see facility_booking.get_available_slots()'s slot-
		splitting fix, which is the other half of this.
		"""
		if not (self.slot_start and self.slot_end):
			return

		# get_time() normalizes both sides to a real datetime.time before
		# comparing, rather than whatever raw form the field holds - see
		# FacilityBooking.validate_times()'s comment for why a plain
		# string/string comparison here would be unsafe.
		start = get_time(self.slot_start)
		end = get_time(self.slot_end)

		if start >= end:
			frappe.throw(_("Row #{0}: Start Time must be before End Time").format(self.idx))

		if not self.slot_duration or self.slot_duration <= 0:
			frappe.throw(_("Row #{0}: Slot Duration must be a positive number of minutes").format(self.idx))

		window_minutes = (
			datetime.combine(datetime.min, end) - datetime.combine(datetime.min, start)
		).total_seconds() / 60
		if self.slot_duration > window_minutes:
			frappe.throw(
				_(
					"Row #{0}: Slot Duration ({1} min) is longer than the {2}–{3} window ({4} min)"
				).format(self.idx, self.slot_duration, self.slot_start, self.slot_end, int(window_minutes))
			)
