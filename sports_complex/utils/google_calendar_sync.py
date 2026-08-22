# Copyright (c) 2026, Your Company and contributors
# For license information, please see license.txt

"""Keeps Confirmed Facility Bookings mirrored onto a Google Calendar.

Frappe's own Google Calendar integration (Integrations > Google Calendar)
only ever pushes/pulls its built-in "Event" doctype - it has no idea
Facility Booking exists. So this module's whole job is to keep one Event
per Confirmed booking in sync: create it the moment a booking becomes
Confirmed, refresh it if called again (idempotent, same as the booking-
status transitions that call it), and delete it if the booking is
cancelled. The actual push to Google happens as a side effect of
Event.save()/frappe.delete_doc() - those already fire Frappe core's own
insert_event_in_google_calendar/update_event_in_google_calendar/
delete_event_from_google_calendar hooks (see frappe/integrations/doctype/
google_calendar), so this module never talks to the Google API directly.

Which calendar to sync to is configured on Sports Complex Setup >
Integrations > Booking Calendar (Google) - leave it blank to turn this off
entirely. That calendar record must already be Enabled and authorized
(the "Authorize Google Calendar Access" button on the Google Calendar
doctype) or the push from Event.save() will silently do nothing until it
runs via the next scheduled sync.

Called directly from facility_booking.py at the exact points booking_status
is actually set to Confirmed/Cancelled (on_submit, mark_paid_and_confirm,
_finalize_cart_bookings, on_cancel) rather than wired through hooks.py's
doc_events - most of those transitions go through db_set()/db_update()
rather than a full save(), which doesn't fire doc_events either way, so a
direct call at the source is the only place this reliably runs.
"""

import frappe
from frappe import _
from frappe.utils import get_datetime


def _get_calendar():
	"""The Google Calendar record configured on Sports Complex Setup, or
	None if sync is switched off (field left blank).
	"""
	return frappe.db.get_single_value("Sports Complex Setup", "google_calendar") or None


def sync_booking_to_calendar(booking):
	"""Create (or refresh, if one already exists) the Event for this
	Confirmed booking. Safe to call more than once for the same booking.

	`booking` is expected to already have booking_status == "Confirmed" -
	callers check that themselves before calling this, same as they
	already gate the rest of their own confirmation logic.
	"""
	calendar = _get_calendar()
	if not calendar:
		return

	if not (booking.court and booking.booking_date and booking.start_time and booking.end_time):
		return

	facility_name = frappe.db.get_value("Sports Facility", booking.court, "facility_name") or booking.court

	event_name = frappe.db.get_value("Facility Booking", booking.name, "google_calendar_event")
	if event_name and frappe.db.exists("Event", event_name):
		event = frappe.get_doc("Event", event_name)
	else:
		event_name = None
		event = frappe.new_doc("Event")
		event.event_type = "Private"

	event.subject = _("{0} - {1}").format(facility_name, booking.customer)
	event.starts_on = get_datetime(f"{booking.booking_date} {booking.start_time}")
	event.ends_on = get_datetime(f"{booking.booking_date} {booking.end_time}")
	event.google_calendar = calendar
	event.sync_with_google_calendar = 1
	event.description = _("Facility Booking: {0}").format(booking.name)

	event.flags.ignore_permissions = True
	event.save()

	if not event_name:
		frappe.db.set_value("Facility Booking", booking.name, "google_calendar_event", event.name)


def remove_booking_from_calendar(booking):
	"""Delete the linked Event (if any) when a booking is cancelled -
	frappe.delete_doc() fires Event's own on_trash hook, which removes it
	from Google the same way deleting any other synced Event would.
	"""
	event_name = frappe.db.get_value("Facility Booking", booking.name, "google_calendar_event")
	if not event_name:
		return

	if frappe.db.exists("Event", event_name):
		frappe.delete_doc("Event", event_name, ignore_permissions=True, force=True)

	frappe.db.set_value("Facility Booking", booking.name, "google_calendar_event", None)
