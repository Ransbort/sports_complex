# Copyright (c) 2026, Your Company and contributors
# For license information, please see license.txt

"""Front-desk check-in/check-out board for Facility Booking - a hand-rolled
desk Page rather than a doctype list view, built after the same idiom as
healthcare's own rehab_portal.py: make_app_page bootstrap on the JS side,
a flat whitelisted-endpoint file here returning either a plain list (read
endpoints) or a {"status": "Success", ...} dict (mutating endpoints).

Deliberately thin: every check-in/check-out mutation here creates and
submits a real Check-In or Check-Out document rather than reimplementing
their validate()/on_submit() rules - see check_in.py/check_out.py for the
actual state-machine logic (status transitions, overage billing). This
page is just a faster front door to those same two doctypes for a front
desk working through a queue of arrivals/departures, instead of
navigating to each doctype's own list and creating records by hand.

get_all_bookings() below is the exception: the two queues above only
ever show Confirmed/Checked-In bookings (that's all either queue can act
on), which means a booking sitting on Payment Pending, Draft, Completed,
Cancelled or No-show was otherwise invisible anywhere on this page -
including a just-created walk-in booking waiting on Sports Complex
Setup's "Require Payment Before Booking Confirmation" gate, which looked
like it had vanished. The "All Bookings" panel (see facility_checkin.js)
exists to close that visibility gap, not to extend the check-in/check-out
state machine itself - it's read-only. There used to be a
mark_booking_paid() write endpoint here too (a "Mark Paid & Confirm"
button, staff attesting a Payment Pending booking's cash/card was already
collected at the desk) that called Facility Booking.mark_paid_and_confirm()
directly. That method only flips the booking's own payment_status/
booking_status fields - every other caller of it (Paystack's webhook in
utils/paystack_hooks.py, Cashier's create_facility_payment_entry()) only
calls it *after* a real Payment Entry has settled the linked Sales
Invoice, so calling it here with no Payment Entry in between left a
booking reading "Confirmed / Paid" while its invoice sat "Unpaid" with no
financial record of the money staff had just said was collected. Real
payment collection for a Payment Pending booking belongs on the Cashier
page (page/cashier/cashier.py's create_facility_payment_entry()), which
creates and submits the Payment Entry first.
"""

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, get_datetime_str, time_diff_in_hours


def _booking_filters(facility=None, date=None, customer=None, facility_booking=None):
	"""Shared AND-filters plus, when a customer search term is given, an
	OR-filter group to go with them.

	customer's Facility Booking.customer field stores the Customer
	*document name* (its Link id, e.g. "CUST-00042"), not the human-
	readable name staff would actually type - a plain LIKE against that
	field almost never matches a typed name, which is why customer search
	looked like it always came back empty. Matching against Customer.
	customer_name (resolved to ids first) as well as the booking's own
	captured email/phone - and the raw id too, in case staff paste that
	instead - covers every way a front-desk person would reasonably search.
	"""
	filters = {"docstatus": 1}
	if facility_booking:
		# Jumping straight to one booking - the Date filter defaults to
		# today and would otherwise silently AND against it, hiding the
		# very booking staff just picked whenever it falls on another day.
		filters["name"] = facility_booking
	else:
		if facility:
			filters["court"] = facility
		if date:
			filters["booking_date"] = date

	or_filters = None
	if customer:
		like = f"%{customer}%"
		matching_customer_ids = frappe.get_all(
			"Customer", filters={"customer_name": ["like", like]}, pluck="name"
		) or [""]
		or_filters = [
			["customer", "in", matching_customer_ids],
			["customer", "like", like],
			["email", "like", like],
			["phone", "like", like],
		]

	return filters, or_filters


def _with_facility_names(bookings):
	facility_names = list({b.court for b in bookings if b.court})
	facility_labels = dict(frappe.get_all(
		"Sports Facility",
		filters={"name": ["in", facility_names]},
		fields=["name", "facility_name"],
		as_list=True,
	)) if facility_names else {}

	for b in bookings:
		b["facility_name"] = facility_labels.get(b.court) or b.court
		b["booking_date"] = str(b.booking_date) if b.booking_date else None
		b["start_time"] = str(b.start_time) if b.start_time else None
		b["end_time"] = str(b.end_time) if b.end_time else None

	return bookings


@frappe.whitelist()
def get_ready_to_check_in(facility=None, date=None, customer=None, facility_booking=None):
	"""Confirmed bookings - eligible for Check-In (see check_in.py's own
	validate(), which enforces the same "Confirmed" requirement, and
	check_in.js's set_query, which enforces it on that doctype's own
	Facility Booking picker).
	"""
	filters, or_filters = _booking_filters(facility, date, customer, facility_booking)
	filters["booking_status"] = "Confirmed"
	bookings = frappe.get_all(
		"Facility Booking",
		filters=filters,
		or_filters=or_filters,
		fields=[
			"name", "customer", "court", "booking_date", "start_time", "end_time",
			"total_amount", "payment_status",
		],
		order_by="booking_date asc, start_time asc",
	)
	return _with_facility_names(bookings)


@frappe.whitelist()
def get_checked_in(facility=None, date=None, customer=None, facility_booking=None):
	"""Checked-In bookings - eligible for Check-Out (see check_out.py's own
	validate(), which enforces the same "Checked-In" requirement).
	"""
	filters, or_filters = _booking_filters(facility, date, customer, facility_booking)
	filters["booking_status"] = "Checked-In"
	bookings = frappe.get_all(
		"Facility Booking",
		filters=filters,
		or_filters=or_filters,
		fields=["name", "customer", "court", "booking_date", "start_time", "end_time", "rate"],
		order_by="booking_date asc, start_time asc",
	)
	bookings = _with_facility_names(bookings)

	check_in_times = dict(frappe.get_all(
		"Check-In",
		filters={"facility_booking": ["in", [b.name for b in bookings]], "docstatus": 1},
		fields=["facility_booking", "check_in_time"],
		as_list=True,
	)) if bookings else {}
	for b in bookings:
		check_in_time = check_in_times.get(b.name)
		b["check_in_time"] = str(check_in_time) if check_in_time else None

	return bookings


@frappe.whitelist()
def check_in_booking(facility_booking, check_in_time=None):
	"""Create and submit a Check-In for this booking - all of the actual
	eligibility/state-transition logic lives on Check-In itself
	(check_in.py's validate()/on_submit()); this is just a front door to it
	instead of the doctype's own New/Save/Submit flow. check_in_time lets
	staff review/adjust the timestamp (e.g. logging a slightly-late arrival)
	before submitting - it defaults to the doctype's own "now" default when
	omitted, same as before this parameter existed.
	"""
	checkin = frappe.new_doc("Check-In")
	checkin.facility_booking = facility_booking
	if check_in_time:
		checkin.check_in_time = get_datetime(check_in_time)
	checkin.insert(ignore_permissions=True)
	checkin.submit()
	return {"status": "Success", "name": checkin.name}


@frappe.whitelist()
def get_checkout_preview(facility_booking, as_of=None):
	"""Live estimate of duration/overage as of `as_of` (defaults to right
	now), for the Check-Out review dialog - the same arithmetic
	Check-Out.calculate_overage() runs for real at submit time (see
	check_out.py), just computed here as a read-only preview. Accepting
	as_of lets staff adjust the check-out time in the dialog and see the
	overage recalculated against that edited time before confirming, rather
	than only ever previewing against the instant the dialog was opened.
	"""
	booking = frappe.db.get_value(
		"Facility Booking",
		facility_booking,
		["booking_status", "booking_date", "end_time", "rate", "customer", "court"],
		as_dict=True,
	)
	if not booking:
		frappe.throw(_("Facility Booking {0} not found").format(facility_booking))
	if booking.booking_status != "Checked-In":
		frappe.throw(
			_("Facility Booking {0} must be Checked-In before check-out (current status: {1})").format(
				facility_booking, booking.booking_status
			)
		)

	check_in_time = frappe.db.get_value(
		"Check-In", {"facility_booking": facility_booking, "docstatus": 1}, "check_in_time"
	)

	now = get_datetime(as_of) if as_of else get_datetime()
	actual_duration = None
	if check_in_time:
		actual_duration = int(round(time_diff_in_hours(now, get_datetime(check_in_time)) * 60))

	scheduled_end = get_datetime(f"{booking.booking_date} {booking.end_time}")
	overage_minutes = int(round(time_diff_in_hours(now, scheduled_end) * 60))
	overage_minutes = overage_minutes if overage_minutes > 0 else 0
	overage_charge = flt(booking.rate) * (overage_minutes / 60) if overage_minutes and booking.rate else 0

	facility_name = frappe.db.get_value("Sports Facility", booking.court, "facility_name") or booking.court

	return {
		"customer": booking.customer,
		"facility_name": facility_name,
		# get_datetime_str() (not str()) matters here: `now`/`check_in_time`
		# are Python datetime objects, and str() on one with a nonzero
		# microsecond component renders "2026-08-22 21:57:10.460546" -
		# fine for display, but "as_of" below is fed straight back in as
		# the default value of the Check-Out dialog's Datetime field, whose
		# control validates/parses that string strictly and rejects the
		# microseconds with a "must be in format: dd-mm-yyyy" error,
		# blocking the dialog. get_datetime_str() formats to Frappe's
		# standard "yyyy-mm-dd HH:mm:ss" (no microseconds), which the
		# control accepts.
		"check_in_time": get_datetime_str(check_in_time) if check_in_time else None,
		"as_of": get_datetime_str(now),
		"actual_duration": actual_duration,
		"overage_minutes": overage_minutes,
		"overage_charge": overage_charge,
	}


@frappe.whitelist()
def check_out_booking(facility_booking, check_out_time=None):
	"""Create and submit a Check-Out for this booking - same idea as
	check_in_booking(): the real overage/billing logic lives on Check-Out
	itself (check_out.py), this just fronts it for the front-desk board.
	check_out_time carries over whatever time staff landed on in the review
	dialog (see get_checkout_preview's as_of) so the submitted document's
	overage matches exactly what they previewed and confirmed.
	"""
	checkout = frappe.new_doc("Check-Out")
	checkout.facility_booking = facility_booking
	if check_out_time:
		checkout.check_out_time = get_datetime(check_out_time)
	checkout.insert(ignore_permissions=True)
	checkout.submit()
	return {
		"status": "Success",
		"name": checkout.name,
		"overage_charge": checkout.overage_charge,
	}


@frappe.whitelist()
def get_all_bookings(facility=None, date=None, customer=None, facility_booking=None):
	"""Every booking matching the board's current filters, any status -
	the read endpoint behind the "All Bookings" panel (see this module's
	own docstring for why that panel exists at all: the two queues above
	only ever show Confirmed/Checked-In, so this is the one place on the
	page a Payment Pending/Draft/Completed/Cancelled/No-show booking is
	visible). Capped at 200 rows, most recent first - a browsing/lookup
	view, not a report; Facility Booking's own list view is still there
	for anything heavier.
	"""
	filters, or_filters = _booking_filters(facility, date, customer, facility_booking)
	bookings = frappe.get_all(
		"Facility Booking",
		filters=filters,
		or_filters=or_filters,
		fields=[
			"name", "customer", "court", "booking_date", "start_time", "end_time",
			"total_amount", "booking_status", "payment_status",
		],
		order_by="booking_date desc, start_time desc",
		limit_page_length=200,
	)
	return _with_facility_names(bookings)
