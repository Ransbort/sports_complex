# Copyright (c) 2026, Your Company and contributors
# For license information, please see license.txt

import calendar
import hashlib
import hmac
import json
from datetime import timedelta

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, get_datetime, get_time, now_datetime, nowdate, time_diff_in_hours
from frappe.utils.password import get_encryption_key

from sports_complex.utils.google_calendar_sync import remove_booking_from_calendar, sync_booking_to_calendar

STAFF_ROLES = {"System Manager", "Sports Complex Manager", "Sports Complex Staff"}


class FacilityBooking(Document):
	def validate(self):
		self.validate_times()
		self.calculate_duration_and_amount()
		self.validate_against_schedule()
		self.validate_max_bookings_per_day()
		self.validate_court_overlap()
		self.validate_maintenance_overlap()

	def validate_times(self):
		# get_time() normalizes both sides to a real datetime.time before
		# comparing - self.start_time/self.end_time can arrive as a plain
		# "H:MM:SS" string (e.g. from create_booking()/create_guest_
		# booking()'s API params, sourced from get_available_slots()'s
		# str(timedelta) output, which drops the leading zero on
		# single-digit hours). Comparing those directly as strings with >=
		# is a lexicographic comparison, not a time comparison, so e.g.
		# "8:00:00" >= "16:00:00" was True (since "8" > "1" as characters)
		# and legitimate bookings were rejected as "Start Time must be
		# before End Time" even though 8am is obviously before 4pm.
		if self.start_time and self.end_time and get_time(self.start_time) >= get_time(self.end_time):
			frappe.throw(_("Start Time must be before End Time"))
		self.validate_booking_window()

	def validate_booking_window(self):
		"""Sports Complex Setup > Facility has had Minimum Booking Notice
		and Advance Booking Window fields since it was first built, but
		nothing ever read them - a booking could be made for a minute from
		now, or for a date years out. Wired here since that's what they're
		named for.
		"""
		if not (self.booking_date and self.start_time):
			return

		settings = frappe.get_cached_doc("Sports Complex Setup")
		booking_start = get_datetime(f"{self.booking_date} {self.start_time}")
		now = now_datetime()

		min_notice_hours = flt(settings.min_booking_notice_hours)
		if min_notice_hours and booking_start < now + timedelta(hours=min_notice_hours):
			frappe.throw(
				_("Bookings must be made at least {0} hour(s) before the start time").format(
					min_notice_hours
				)
			)

		advance_days = cint(settings.advance_booking_window_days)
		if advance_days and booking_start > now + timedelta(days=advance_days):
			frappe.throw(
				_("Bookings cannot be made more than {0} day(s) in advance").format(advance_days)
			)

	def validate_against_schedule(self):
		"""Booking Schedule models per-court, per-day-of-week open slots but
		nothing ever validated a booking against it - a court could be
		booked at 3am even if its Booking Schedule says it's only open
		6am-10pm. Only enforced once a court actually has at least one
		active Booking Schedule row, so courts nobody has configured a
		schedule for yet keep working exactly as before (unrestricted).
		"""
		if not (self.court and self.booking_date and self.start_time and self.end_time):
			return

		has_any_schedule = frappe.db.exists("Booking Schedule", {"court": self.court, "is_active": 1})
		if not has_any_schedule:
			return

		day_of_week = get_datetime(self.booking_date).strftime("%A")
		covering_slot = frappe.db.exists(
			"Booking Schedule",
			{
				"court": self.court,
				"day_of_week": day_of_week,
				"is_active": 1,
				"slot_start": ("<=", self.start_time),
				"slot_end": (">=", self.end_time),
			},
		)
		if not covering_slot:
			frappe.throw(
				_("Court {0} has no open slot covering {1}-{2} on a {3}").format(
					self.court, self.start_time, self.end_time, day_of_week
				)
			)

	def validate_max_bookings_per_day(self):
		if not (self.customer and self.booking_date):
			return

		limit = cint(
			frappe.db.get_single_value("Sports Complex Setup", "max_bookings_per_member_per_day")
		)
		if not limit:
			return  # 0 = unlimited, per the field's own description

		existing = frappe.db.count(
			"Facility Booking",
			{
				"customer": self.customer,
				"booking_date": self.booking_date,
				"name": ("!=", self.name or ""),
				"docstatus": ("<", 2),
				"booking_status": ("not in", ["Cancelled", "No-show"]),
			},
		)
		if existing >= limit:
			frappe.throw(
				_("{0} already has {1} booking(s) on {2} - the maximum allowed per day").format(
					self.customer, existing, self.booking_date
				)
			)

	def calculate_duration_and_amount(self):
		if self.start_time and self.end_time:
			# start_time/end_time are timedelta objects on Time fields; combine
			# with booking_date to get a duration in minutes.
			start = get_datetime(f"{self.booking_date} {self.start_time}")
			end = get_datetime(f"{self.booking_date} {self.end_time}")
			hours = time_diff_in_hours(end, start)
			self.duration = int(round(hours * 60))

			if self.rate:
				self.total_amount = flt(self.rate) * hours

	def validate_court_overlap(self):
		if not (self.court and self.booking_date and self.start_time and self.end_time):
			return

		if cint(frappe.db.get_single_value("Sports Complex Setup", "allow_overlapping_bookings")):
			return

		# Lock the Sports Facility row for the rest of this transaction so
		# two near-simultaneous submissions for the same facility can't
		# both read "no conflict" here before either has actually
		# committed - a classic check-then-act race. Without this, two
		# customers hitting create_booking() for the same slot at the same
		# moment could both pass this check and end up with two confirmed
		# bookings for one facility.
		frappe.db.sql("select name from `tabSports Facility` where name=%s for update", (self.court,))

		check_start, check_end = self.start_time, self.end_time
		buffer_minutes = flt(
			frappe.db.get_single_value("Sports Complex Setup", "buffer_time_between_bookings")
		)
		if buffer_minutes:
			# start_time/end_time come back from the DB as timedelta objects
			# (Time fieldtype) - widen this booking's own range by the
			# configured buffer on both sides before comparing, so the gap
			# between any two bookings on the same court ends up >= buffer.
			pad = timedelta(minutes=buffer_minutes)
			check_start, check_end = self.start_time - pad, self.end_time + pad

		conflicting = frappe.db.sql(
			"""
			select name
			from `tabFacility Booking`
			where court = %(court)s
				and booking_date = %(booking_date)s
				and name != %(name)s
				and docstatus < 2
				and booking_status not in ('Cancelled', 'No-show')
				and start_time < %(end_time)s
				and end_time > %(start_time)s
			limit 1
			""",
			{
				"court": self.court,
				"booking_date": self.booking_date,
				"name": self.name or "",
				"start_time": check_start,
				"end_time": check_end,
			},
		)
		if conflicting:
			frappe.throw(
				_("Court {0} is already booked for an overlapping time on {1} ({2})").format(
					self.court, self.booking_date, conflicting[0][0]
				)
			)

	def validate_maintenance_overlap(self):
		"""Delegates to Sports Facility.is_under_maintenance() (moved there
		from the retired Court doctype - see that method's docstring)
		rather than maintaining a second copy of the same query here.
		"""
		if not (self.court and self.booking_date and self.start_time and self.end_time):
			return

		facility = frappe.get_cached_doc("Sports Facility", self.court)
		if facility.is_under_maintenance(self.booking_date, self.start_time, self.end_time):
			frappe.throw(
				_("Facility {0} has scheduled maintenance overlapping this time on {1}").format(
					self.court, self.booking_date
				)
			)

	def on_submit(self):
		if self.flags.cart_mode:
			# Multi-slot cart booking (see create_booking_cart()/create_
			# guest_booking_cart()) - invoicing and booking_status are
			# handled once, together, for every booking in the cart after
			# all of them have submitted successfully, rather than each
			# booking creating (and the customer having to separately pay)
			# its own invoice - see _run_cart().
			return

		self.create_sales_invoice()

		settings = frappe.get_cached_doc("Sports Complex Setup")
		if cint(settings.enable_paystack_payments) and cint(settings.require_payment_before_confirmation):
			# Held at Payment Pending until frappe_paystack confirms the
			# invoice is paid - see mark_paid_and_confirm() and
			# utils/paystack_hooks.py. Previously this jumped straight to
			# Confirmed on submit regardless of payment, which is what
			# "Require Payment Before Booking Confirmation" is supposed to
			# prevent.
			self.booking_status = "Payment Pending"
		else:
			self.booking_status = "Confirmed"
		self.db_update()

		if self.booking_status == "Confirmed":
			sync_booking_to_calendar(self)

	def on_cancel(self):
		self.db_set("booking_status", "Cancelled")
		remove_booking_from_calendar(self)

	def mark_paid_and_confirm(self):
		"""Called once frappe_paystack confirms payment against this
		booking's Sales Invoice - see utils/paystack_hooks.py. Idempotent:
		a webhook delivery and the checkout page's synchronous
		verify_transaction() fallback can both fire for the same payment,
		and this shouldn't double-apply either way.
		"""
		if self.payment_status == "Paid" and self.booking_status not in ("Draft", "Payment Pending"):
			return
		self.db_set("payment_status", "Paid")
		if self.booking_status == "Payment Pending":
			self.db_set("booking_status", "Confirmed")
			sync_booking_to_calendar(self)

	def create_sales_invoice(self):
		"""Create the linked Sales Invoice that frappe_paystack will take payment against.

		NOTE: this assumes Sales Invoice has a custom Link field
		`facility_booking` (see schema doc section 6 — add via Customize
		Form or a fixtures JSON).

		The Item billed is Sports Facility.billing_item when the facility
		has one set - that's the explicit, per-facility override this
		method used to lack, which meant every facility of a given
		Facility Type was stuck billing against one Item literally named
		the same as that Facility Type. Facilities that haven't set
		billing_item yet fall back to that same name-matching convention,
		so nothing already relying on it breaks.
		"""
		if self.sales_invoice:
			return

		facility_type, billing_item = frappe.db.get_value(
			"Sports Facility", self.court, ["facility_type", "billing_item"]
		)
		item_code = billing_item or facility_type

		if not item_code or not frappe.db.exists("Item", item_code):
			frappe.throw(
				_(
					"No billing Item configured for facility {0}. Set a Billing Item on the "
					"Sports Facility (or create a sellable Item named {1}) before confirming "
					"bookings."
				).format(self.court, facility_type or "")
			)

		si = frappe.new_doc("Sales Invoice")
		si.customer = self.customer
		si.facility_booking = self.name
		si.append(
			"items",
			{
				"item_code": item_code,
				"qty": 1,
				"rate": self.total_amount or self.rate or 0,
			},
		)
		si.flags.ignore_permissions = True
		si.insert()
		# Left as Draft (docstatus 0) before this, which is invalid to
		# attach a payment link to - frappe_paystack's create_payment_link()
		# (called from get_booking_payment_link() whenever booking_status
		# lands on Payment Pending) needs a submitted Sales Invoice, and
		# was failing with "Document has been cancelled or in draft."
		si.submit()

		self.sales_invoice = si.name


@frappe.whitelist()
def get_booking_events(start, end, filters=None):
	"""Feed the Calendar view for Facility Booking.

	Combines booking_date + start_time/end_time into datetimes since the
	doctype stores date and time separately rather than as combined
	datetime fields. Registered in facility_booking.js via
	get_events_method.
	"""
	conditions = ["booking_date between %(start)s and %(end)s"]
	values = {"start": start, "end": end}

	if filters:
		filters = frappe.parse_json(filters)
		if filters.get("court"):
			conditions.append("court = %(court)s")
			values["court"] = filters["court"]
		if filters.get("booking_status"):
			conditions.append("booking_status = %(booking_status)s")
			values["booking_status"] = filters["booking_status"]

	bookings = frappe.db.sql(
		f"""
		select name, customer, court, booking_date, start_time, end_time,
			booking_status, payment_status
		from `tabFacility Booking`
		where {" and ".join(conditions)}
		""",
		values,
		as_dict=True,
	)

	events = []
	for b in bookings:
		events.append(
			{
				"name": b.name,
				"title": f"{b.court} - {b.customer}",
				"start": get_datetime(f"{b.booking_date} {b.start_time}"),
				"end": get_datetime(f"{b.booking_date} {b.end_time}"),
				"status": b.booking_status,
				"payment_status": b.payment_status,
			}
		)
	return events


# ---------------------------------------------------------------------
# Self-service booking API
#
# Everything below is new: previously Facility Booking was reachable only
# from the desk, so a customer could never book (or pay for) a court
# without a staff member operating the form for them. This gives a
# logged-in member/customer their own entry points, built on the same
# validate() chain above rather than duplicating its rules.
#
# Guest booking (no login at all) isn't supported yet - Member has no
# linked User today, so there's no way to verify who an anonymous caller
# actually is. See BOOKING_RECOMMENDATIONS.md for the HMAC
# guest-access-token pattern (borrowed from the buzz app) this would want
# if guest booking is added later.
# ---------------------------------------------------------------------


def resolve_session_customer():
	"""Resolve the logged-in portal user to their Customer via Contact.

	Delegates to frappe_paystack's resolve_customer_by_email() - the
	version that used to live here directly (frappe.db.get_value(
	"Contact", {"email_id": ...}, "customer")) copied a bug that was
	already present in frappe_paystack's own my-payments/my-payment
	pages: "customer" isn't a real column on Contact (a Customer links to
	a Contact via the Dynamic Link child table, not a fetched field), so
	it would have raised an "Unknown column" SQL error the first time
	this actually ran against a real Contact record. Fixed in one place
	now that frappe_paystack is a declared required_apps dependency (see
	hooks.py) rather than duplicated here to avoid one.
	"""
	if not frappe.session.user or frappe.session.user == "Guest":
		return None
	from frappe_paystack.utils import resolve_customer_by_email

	return resolve_customer_by_email(frappe.session.user)


def _is_booking_staff():
	return bool(set(frappe.get_roles()) & STAFF_ROLES)


def get_booking_access_token(booking_name):
	"""HMAC of the booking name, signed with the site's own encryption
	key. Lets a guest who was never logged in (and never will be, for
	this booking) view/pay for/cancel their own booking through a signed
	link, while keeping booking names unguessable by enumeration - same
	construction the buzz app uses for its guest ticket-booking access
	(get_booking_access_token in api/booking/services.py) - see
	BOOKING_RECOMMENDATIONS.md.
	"""
	key = get_encryption_key().encode()
	return hmac.new(key, booking_name.encode(), hashlib.sha256).hexdigest()


def verify_booking_access_token(booking_name, token):
	return bool(token) and hmac.compare_digest(get_booking_access_token(booking_name), token)


def _ensure_booking_access(booking, session_customer=None, token=None):
	"""Staff can always act on any booking; a logged-in customer only on
	their own (mirrors the ownership check frappe_paystack's my-payment
	page uses, for the same reason: stop one customer reading or paying
	for another customer's booking by guessing/incrementing a booking
	name); a guest with a valid access token only on the one booking that
	token was issued for.
	"""
	if _is_booking_staff():
		return
	if verify_booking_access_token(booking.name, token):
		return
	if not session_customer or session_customer != booking.customer:
		frappe.throw(_("You are not allowed to access this booking"), frappe.PermissionError)


@frappe.whitelist(allow_guest=True)
def get_available_slots(sports_facility, date):
	"""List the open time ranges for a facility on a given date: each
	active Booking Schedule slot for that facility/day-of-week, minus
	whatever's already booked (Facility Booking) or under maintenance
	(Maintenance Schedule), keeping Sports Complex Setup's Buffer Time
	Between Bookings clear around each busy interval.

	This is the "can I book this?" counterpart to the buzz app's
	Event Ticket Type.remaining_tickets - see BOOKING_RECOMMENDATIONS.md.
	allow_guest=True because this is read-only availability info, not a
	booking action - browsing what's open shouldn't require logging in.

	Booking Schedule/Facility Booking/Maintenance Schedule all still store
	this under a column literally named `court` (kept for backward
	compatibility with existing data - see the retired Court doctype's
	migration patch), which is why it's used as the filter key below even
	though the parameter here is named for what it actually holds now.
	"""
	day_of_week = get_datetime(date).strftime("%A")

	template_slots = frappe.get_all(
		"Booking Schedule",
		filters={"court": sports_facility, "day_of_week": day_of_week, "is_active": 1},
		fields=["slot_start", "slot_end", "slot_duration"],
		order_by="slot_start asc",
	)
	if not template_slots:
		return []

	buffer_minutes = flt(
		frappe.db.get_single_value("Sports Complex Setup", "buffer_time_between_bookings")
	)

	busy = []
	for row in frappe.get_all(
		"Facility Booking",
		filters={
			"court": sports_facility,
			"booking_date": date,
			"docstatus": ("<", 2),
			"booking_status": ("not in", ["Cancelled", "No-show"]),
		},
		fields=["start_time", "end_time"],
	):
		busy.append(_padded(row.start_time, row.end_time, buffer_minutes))

	for row in frappe.get_all(
		"Maintenance Schedule",
		# NOTE: was also filtering on docstatus=1 - Maintenance Schedule is
		# not submittable (is_submittable: 0 in maintenance_schedule.json),
		# so docstatus is permanently 0 and that filter matched nothing,
		# ever. Same bug class as the one fixed in
		# validate_maintenance_overlap() above: this meant a slot under
		# active maintenance was never actually subtracted from
		# availability here, so guests could see and book a maintenance
		# slot as "open".
		filters={
			"court": sports_facility,
			"scheduled_date": date,
			"status": ("!=", "Completed"),
		},
		fields=["scheduled_start", "scheduled_end"],
	):
		if row.scheduled_start and row.scheduled_end:
			busy.append((row.scheduled_start, row.scheduled_end))

	slots = []
	for template in template_slots:
		for free_start, free_end in _subtract_busy(template.slot_start, template.slot_end, busy):
			for slot_start, slot_end in _split_into_slots(free_start, free_end, template.slot_duration):
				slots.append(
					{
						"start_time": _format_time(slot_start),
						"end_time": _format_time(slot_end),
						"slot_duration": template.slot_duration,
					}
				)
	return slots


@frappe.whitelist(allow_guest=True)
def get_month_availability(sports_facility, year, month):
	"""Per-day open-slot counts for a facility across one calendar month -
	powers the /book-facility date picker's "highlight the days that still
	have openings" view without a round trip per day clicked. Reuses
	get_available_slots() day by day rather than a bulk query; fine at
	this booking system's scale (a handful of facilities, ~30 days) -
	would be worth batching into fewer queries if the facility/day count
	grows a lot.

	Days before today come back as 0 without being queried - the past
	can't be booked regardless of what the schedule says.
	"""
	year = cint(year)
	month = cint(month)
	_, days_in_month = calendar.monthrange(year, month)

	today = get_datetime(nowdate()).date()
	availability = {}
	for day in range(1, days_in_month + 1):
		date_str = f"{year:04d}-{month:02d}-{day:02d}"
		if get_datetime(date_str).date() < today:
			availability[date_str] = 0
			continue
		availability[date_str] = len(get_available_slots(sports_facility, date_str))
	return availability


def _format_time(value):
	"""Render a Time-fieldtype value (frappe.get_all returns these as
	datetime.timedelta) as a zero-padded "HH:MM:SS" string. Plain str() on
	a timedelta drops the leading zero on single-digit hours - str(
	timedelta(hours=8)) is "8:00:00", not "08:00:00" - which is harmless
	to display but breaks any later string comparison of two such values
	(e.g. "8:00:00" >= "16:00:00" is True lexicographically). See
	validate_times()'s comment for the bug that caused.
	"""
	total_seconds = int(value.total_seconds()) if isinstance(value, timedelta) else int(value)
	hours, remainder = divmod(total_seconds, 3600)
	minutes, seconds = divmod(remainder, 60)
	return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _padded(start_time, end_time, buffer_minutes):
	if not buffer_minutes:
		return (start_time, end_time)
	pad = timedelta(minutes=buffer_minutes)
	return (start_time - pad, end_time + pad)


def _subtract_busy(slot_start, slot_end, busy_ranges):
	"""Subtract every (start, end) pair in busy_ranges from [slot_start,
	slot_end), returning the remaining free sub-ranges in order. Plain
	interval subtraction - busy_ranges need not be sorted or
	non-overlapping.
	"""
	free = [(slot_start, slot_end)]
	for busy_start, busy_end in busy_ranges:
		next_free = []
		for free_start, free_end in free:
			if busy_end <= free_start or busy_start >= free_end:
				next_free.append((free_start, free_end))
				continue
			if busy_start > free_start:
				next_free.append((free_start, busy_start))
			if busy_end < free_end:
				next_free.append((busy_end, free_end))
		free = next_free
	return free


def _split_into_slots(start, end, duration_minutes):
	"""Chop one open [start, end) range into consecutive, back-to-back
	duration_minutes-long bookable slots.

	Previously get_available_slots() returned each free range from
	_subtract_busy() as-is - a facility open 8:00-16:00 with nothing
	booked yet came back as a single "8:00-16:00" slot instead of eight
	1-hour ones, so the very first guest to book that facility any given
	day could only ever book the whole day at once. Sports Facility Time
	Slot.validate() now guarantees slot_duration is a positive number
	that fits inside its own window at least once, but a leftover
	remainder shorter than a full slot at the tail of a range (e.g. a
	40-minute gap left after subtracting a busy booking, with a
	60-minute slot_duration) is simply dropped rather than offered as a
	too-short booking.
	"""
	if not duration_minutes or duration_minutes <= 0:
		return []

	step = timedelta(minutes=duration_minutes)
	slots = []
	cursor = start
	while cursor + step <= end:
		slots.append((cursor, cursor + step))
		cursor += step
	return slots


def _send_booking_confirmation_email(email, bookings, tokens=None):
	"""Best-effort confirmation email after a booking (or a whole cart of
	them) is created - summarizes what was booked and links back to the
	individual booking(s) plus My Bookings, so the customer/guest doesn't
	have to keep the confirmation page open to find a booking again
	later.

	tokens, when given, maps booking name -> guest access token (see
	get_booking_access_token) so a guest's link works without a session;
	omitted for a logged-in customer, whose session alone is enough for
	get_booking_status()/_ensure_booking_access() to recognise them.

	Failure here (bad SMTP config, transient error) is logged, not
	raised - the booking itself has already succeeded by the time this
	runs, so an email hiccup shouldn't turn into a failed booking
	response for the caller.
	"""
	email = (email or "").strip().lower()
	if not email or "@" not in email or not bookings:
		return

	tokens = tokens or {}
	site_url = frappe.utils.get_url()
	facility_names = {}
	rows = []
	for booking in bookings:
		if booking.court not in facility_names:
			facility_names[booking.court] = (
				frappe.db.get_value("Sports Facility", booking.court, "facility_name") or booking.court
			)

		link = f"{site_url}/booking-confirmation/{booking.name}"
		token = tokens.get(booking.name)
		if token:
			link += f"?token={token}"

		rows.append(
			"<tr>"
			f"<td style='padding:4px 16px 4px 0'>{facility_names[booking.court]}</td>"
			f"<td style='padding:4px 16px 4px 0'>{booking.booking_date}</td>"
			f"<td style='padding:4px 16px 4px 0'>{booking.start_time} - {booking.end_time}</td>"
			f"<td style='padding:4px 16px 4px 0'>{frappe.utils.fmt_money(booking.total_amount or 0)}</td>"
			f"<td style='padding:4px 0'><a href='{link}'>View</a></td>"
			"</tr>"
		)

	my_bookings_url = f"{site_url}/my-bookings"
	message = f"""
		<p>Thanks for your booking! Here's a summary:</p>
		<table style="border-collapse: collapse">
			<thead>
				<tr>
					<th style="text-align:left; padding:4px 16px 4px 0">Facility</th>
					<th style="text-align:left; padding:4px 16px 4px 0">Date</th>
					<th style="text-align:left; padding:4px 16px 4px 0">Time</th>
					<th style="text-align:left; padding:4px 16px 4px 0">Amount</th>
					<th></th>
				</tr>
			</thead>
			<tbody>
				{"".join(rows)}
			</tbody>
		</table>
		<p>You can check your bookings anytime at <a href="{my_bookings_url}">{my_bookings_url}</a>.</p>
	"""

	try:
		frappe.sendmail(
			recipients=[email],
			subject=_("Your booking confirmation"),
			message=message,
			now=True,
		)
	except Exception:
		frappe.log_error(
			title="Sports Complex: could not send booking confirmation email",
			message=frappe.get_traceback(),
		)


def auto_cancel_unpaid_bookings():
	"""Scheduled hourly (see hooks.py's scheduler_events). A booking stuck
	at "Payment Pending" - submitted and invoiced, but never paid (see
	on_submit()'s Require Payment Before Booking Confirmation gate) - held
	its slot indefinitely with nothing to ever clean it up. Cancels any
	left unpaid for longer than Sports Complex Setup's Auto Cancel Unpaid
	Bookings After (hours) - a no-op (0) leaves this disabled, same
	"falsy setting = off" convention as every other Sports Complex Setup
	threshold in this file.

	Goes through a real, submitted Booking Cancellation rather than
	poking booking_status directly, so this stays on the exact same path
	as a guest's own self-service cancellation (request_cancellation()) -
	whatever side effects that path has (or gains later) apply here too.
	No refund_amount is set: nothing was ever paid, so there's nothing to
	credit back.

	Also voids the booking's own Sales Invoice (see _void_unpaid_invoice) -
	previously left behind as a live, submitted, Unpaid document forever.
	Beyond cluttering accounting reports with outstanding revenue for a
	slot nobody holds anymore, a guest with a stale "Pay Now" tab open
	from before the cancellation could still complete payment against it,
	since nothing checked booking_status before honoring that link -
	get_booking_payment_link() now also refuses once booking_status has
	moved off Payment Pending, so this is closed from both ends.
	"""
	hours = flt(frappe.get_cached_doc("Sports Complex Setup").auto_cancel_unpaid_bookings_after_hours)
	if not hours:
		return

	cutoff = now_datetime() - timedelta(hours=hours)
	stale = frappe.get_all(
		"Facility Booking",
		filters={"booking_status": "Payment Pending", "docstatus": 1, "creation": ["<", cutoff]},
		fields=["name", "sales_invoice"],
	)
	for booking in stale:
		try:
			cancellation = frappe.new_doc("Booking Cancellation")
			cancellation.facility_booking = booking.name
			cancellation.reason = _("Auto-cancelled: payment not received within {0} hour(s)").format(hours)
			cancellation.flags.ignore_permissions = True
			cancellation.insert()
			cancellation.submit()
		except Exception:
			frappe.log_error(
				title="Sports Complex: could not auto-cancel unpaid booking",
				message=frappe.get_traceback(),
			)
			continue

		_void_unpaid_invoice(booking.sales_invoice)


def _void_unpaid_invoice(sales_invoice):
	"""Cancel the Sales Invoice behind a booking that just got auto-
	cancelled for non-payment - see auto_cancel_unpaid_bookings(). Only
	ever cancels a genuinely unpaid invoice: Sales Invoice.cancel() itself
	throws if any Payment Entry/GL entry is linked against it, so a
	booking that (despite sitting at Payment Pending) somehow already has
	money against it is left alone and logged rather than force-voided.

	A cart invoice can bill more than one Facility Booking together (see
	_create_cart_invoice()) - only voids it if every booking still tied to
	it is itself unpaid (Payment Pending or already Cancelled). Paystack
	settles a cart's shared invoice in one shot (the full amount or
	nothing), so a paid sibling alongside an unpaid one on the same
	invoice shouldn't happen under the current flow, but this is the one
	place a bug in that assumption would do real damage - cancelling a
	paying guest's invoice out from under them - so it's worth checking
	directly here rather than trusting the invariant blindly. Safe to call
	more than once for the same invoice (one cart can have several stale
	bookings in the same run): the docstatus check below makes every call
	after the first a no-op.
	"""
	if not sales_invoice:
		return

	unpaid_statuses = {"Payment Pending", "Cancelled"}
	linked_statuses = frappe.get_all(
		"Facility Booking",
		filters={"sales_invoice": sales_invoice},
		pluck="booking_status",
	)
	if any(status not in unpaid_statuses for status in linked_statuses):
		return

	try:
		invoice = frappe.get_doc("Sales Invoice", sales_invoice)
		if invoice.docstatus != 1:
			return
		invoice.flags.ignore_permissions = True
		invoice.cancel()
	except Exception:
		frappe.log_error(
			title="Sports Complex: could not void unpaid invoice for auto-cancelled booking",
			message=frappe.get_traceback(),
		)


def mark_no_shows():
	"""Scheduled hourly (see hooks.py's scheduler_events). Nothing ever
	moves a booking off "Confirmed" except Check-In (-> "Checked-In") or a
	Booking Cancellation (-> "Cancelled") - so a booking still sitting at
	"Confirmed" once its own end_time is in the past means the guest
	never checked in and never cancelled either: a no-show.

	Records Sports Complex Setup's No Show Penalty % of Total Amount on
	the booking (no_show_penalty_amount) purely for staff visibility/
	reporting - the guest already paid Total Amount in full to reach
	Confirmed in the first place, so there's no new invoice to create
	here, just a record of how much of that payment the business is
	entitled to keep if the guest never asks for a refund. A Booking
	Cancellation raised after the fact is what actually caps any such
	refund by this same percentage - see BookingCancellation.
	apply_no_show_penalty().
	"""
	penalty_pct = flt(frappe.get_cached_doc("Sports Complex Setup").no_show_penalty_)
	now = now_datetime()

	candidates = frappe.get_all(
		"Facility Booking",
		filters={"booking_status": "Confirmed", "docstatus": 1},
		fields=["name", "booking_date", "end_time", "total_amount"],
	)
	for booking in candidates:
		if not (booking.booking_date and booking.end_time):
			continue
		if get_datetime(f"{booking.booking_date} {booking.end_time}") >= now:
			continue
		try:
			frappe.db.set_value(
				"Facility Booking",
				booking.name,
				{
					"booking_status": "No-show",
					"no_show_penalty_amount": (flt(booking.total_amount) * penalty_pct / 100) if penalty_pct else 0,
				},
			)
		except Exception:
			frappe.log_error(
				title="Sports Complex: could not mark booking as No-show",
				message=frappe.get_traceback(),
			)


def send_booking_reminders():
	"""Scheduled hourly (see hooks.py's scheduler_events). Reminds a
	guest/customer of a Confirmed booking whose start time falls inside
	Sports Complex Setup's Reminder Lead Time (hours) - a no-op unless
	Send Booking Reminder is checked there. reminder_sent guards against
	re-sending: this job runs far more often than once per booking's own
	lead window, and would otherwise catch (and re-email) the same
	booking on every run until its start time passed.
	"""
	settings = frappe.get_cached_doc("Sports Complex Setup")
	if not cint(settings.send_booking_reminder):
		return
	lead_hours = flt(settings.reminder_lead_time_hours)
	if not lead_hours:
		return

	now = now_datetime()
	window_end = now + timedelta(hours=lead_hours)

	candidates = frappe.get_all(
		"Facility Booking",
		filters={
			"booking_status": "Confirmed",
			"docstatus": 1,
			"reminder_sent": 0,
			# Coarse date-only pre-filter - start_time is a separate Time
			# field, so the precise [now, window_end] cutoff is re-checked
			# in Python below.
			"booking_date": ["between", [now.date(), window_end.date()]],
		},
		fields=["name", "email", "court", "booking_date", "start_time", "end_time"],
	)

	for booking in candidates:
		if not (booking.booking_date and booking.start_time):
			continue
		booking_start = get_datetime(f"{booking.booking_date} {booking.start_time}")
		if not (now <= booking_start <= window_end):
			continue
		if booking.email:
			_send_booking_reminder_email(booking)
		try:
			frappe.db.set_value("Facility Booking", booking.name, "reminder_sent", 1)
		except Exception:
			frappe.log_error(
				title="Sports Complex: could not mark booking reminder as sent",
				message=frappe.get_traceback(),
			)


def _send_booking_reminder_email(booking):
	"""Best-effort, same rationale as _send_booking_confirmation_email():
	the reminder run itself shouldn't fail because one booking's email
	address bounces or SMTP hiccups - log it and move on to the rest.
	"""
	facility_name = frappe.db.get_value("Sports Facility", booking.court, "facility_name") or booking.court
	site_url = frappe.utils.get_url()
	link = f"{site_url}/booking-confirmation/{booking.name}"

	message = f"""
		<p>This is a reminder that your booking is coming up soon:</p>
		<table style="border-collapse: collapse">
			<tbody>
				<tr><td style="padding:4px 16px 4px 0">Facility</td><td>{frappe.utils.escape_html(facility_name)}</td></tr>
				<tr><td style="padding:4px 16px 4px 0">Date</td><td>{booking.booking_date}</td></tr>
				<tr><td style="padding:4px 16px 4px 0">Time</td><td>{booking.start_time} - {booking.end_time}</td></tr>
			</tbody>
		</table>
		<p><a href="{link}">View your booking</a></p>
	"""

	try:
		frappe.sendmail(
			recipients=[booking.email],
			subject=_("Reminder: your upcoming booking"),
			message=message,
			now=True,
		)
	except Exception:
		frappe.log_error(
			title="Sports Complex: could not send booking reminder email",
			message=frappe.get_traceback(),
		)


def _resolve_member_contact(customer):
	"""Best-effort email/phone lookup for a logged-in customer's booking,
	so Facility Booking carries its own copy of who to reach rather than
	staff having to open the linked Customer/Member record to find out -
	same rationale as create_guest_booking() already storing the guest's
	email/phone directly on the booking.

	Member is this app's own source of truth for contact details (see
	resolve_or_create_guest_customer()) - every Customer created through
	the booking flow, guest or otherwise, has one. Falls back to the
	logged-in portal user's own login id for email when there's no Member
	record to check, since that id is always an email address - see
	resolve_session_customer()'s use of resolve_customer_by_email().
	"""
	email, phone = frappe.db.get_value("Member", {"customer": customer}, ["email", "phone"]) or (None, None)
	if not email and frappe.session.user and "@" in frappe.session.user:
		email = frappe.session.user
	return email, phone


@frappe.whitelist()
def create_booking(sports_facility, booking_date, start_time, end_time, notes=None):
	"""Self-service entry point for a logged-in member/customer to book a
	facility themselves. Runs the exact same validate() chain a staff-
	created booking goes through (overlap, maintenance, schedule,
	notice-window, per-day limit) - ignore_permissions only bypasses
	Facility Booking's desk-only create/submit permissions, which is what
	this whitelisted method's own ownership check (resolve_session_
	customer requiring a real, logged-in Customer) exists to replace.

	Returns a Paystack payment link alongside the booking whenever the
	booking lands on Payment Pending, so the caller can send the customer
	straight to checkout in one step.
	"""
	customer = resolve_session_customer()
	if not customer:
		frappe.throw(
			_("No Customer record is linked to your account. Contact the front desk to book."),
			frappe.PermissionError,
		)

	email, phone = _resolve_member_contact(customer)

	booking = frappe.new_doc("Facility Booking")
	booking.customer = customer
	booking.court = sports_facility
	booking.booking_date = booking_date
	booking.start_time = start_time
	booking.end_time = end_time
	booking.notes = notes
	booking.email = email
	booking.phone = phone
	booking.rate = frappe.get_cached_doc("Sports Facility", sports_facility).get_effective_hourly_rate()
	booking.flags.ignore_permissions = True
	booking.insert()
	booking.submit()

	_send_booking_confirmation_email(email, [booking])

	result = {"booking": booking.name, "booking_status": booking.booking_status}
	if booking.booking_status == "Payment Pending":
		result["payment_link"] = get_booking_payment_link(booking.name)
	return result


@frappe.whitelist()
def create_staff_booking(customer, sports_facility, booking_date, start_time, end_time, notes=None):
	"""Front-desk counterpart to create_booking(): lets staff on the
	Facility Check-In board (see facility_checkin.js's "Book Facility"
	button) book a facility on behalf of a walk-in/phone customer, with
	the Customer picked explicitly instead of resolved from the logged-in
	session. This is the front door create_booking()'s own error message
	already points staff without a linked Customer record at ("Contact
	the front desk to book") - until now nothing on the desk side actually
	answered that.

	Runs through the exact same validate() chain (overlap, maintenance,
	schedule, notice-window, per-day limit) as every other booking-
	creation entry point in this file - only the *source* of the customer
	differs, not the rules a booking has to pass.

	No mark_paid attestation here (there used to be one, calling
	FacilityBooking.mark_paid_and_confirm() directly) - that only ever
	flips this booking's own payment_status/booking_status fields, it
	never touches the linked Sales Invoice, so the invoice was left
	sitting "Unpaid" with no Payment Entry for the money staff had just
	told this to consider collected. A booking created here that's
	actually been paid for in person should have that payment collected
	through the Cashier page instead (page/cashier/cashier.py's
	create_facility_payment_entry()), which creates and submits a real
	Payment Entry before bringing the booking's own status fields in
	line - the same accounting-grade path Paystack's own webhook goes
	through (utils/paystack_hooks.py).

	Restricted to Sports Complex Staff/Manager/System Manager (mirrors
	Facility Booking's own permissions and Facility Check-In's page
	roles) since, unlike create_booking(), the caller supplies the
	customer rather than it being derived from who's logged in.
	"""
	if not _is_booking_staff():
		frappe.throw(_("Not permitted to book on behalf of a customer"), frappe.PermissionError)

	if not frappe.db.exists("Customer", customer):
		frappe.throw(_("Customer {0} not found").format(customer))

	email, phone = _resolve_member_contact(customer)

	booking = frappe.new_doc("Facility Booking")
	booking.customer = customer
	booking.court = sports_facility
	booking.booking_date = booking_date
	booking.start_time = start_time
	booking.end_time = end_time
	booking.notes = notes
	booking.email = email
	booking.phone = phone
	booking.rate = frappe.get_cached_doc("Sports Facility", sports_facility).get_effective_hourly_rate()
	booking.flags.ignore_permissions = True
	booking.insert()
	booking.submit()

	_send_booking_confirmation_email(email, [booking])

	return {"booking": booking.name, "booking_status": booking.booking_status}


# ---------------------------------------------------------------------
# Cart booking (multiple slots, one payment)
#
# create_booking()/create_guest_booking() above still exist and still work
# for a single slot, but the /book-facility page itself now always goes
# through the cart entry points below (a size-1 cart is just the n=1
# case) so a customer can select several time slots - same facility,
# different days if they like - in one visit and pay for all of them in
# one Paystack checkout instead of one checkout per slot.
# ---------------------------------------------------------------------


def _parse_slots(slots):
	"""slots arrives from frappe.call() as a JSON-encoded string - Frappe's
	client-side request layer JSON.stringifies array/object args before
	sending them - so this needs the same defensive frappe.parse_json()
	pattern get_booking_events() already uses for its own filters param;
	only actually parses it when it's still a string (so this also works
	if something calls in with an already-decoded list, e.g. from Python).
	"""
	if isinstance(slots, str):
		slots = frappe.parse_json(slots)
	if not slots or not isinstance(slots, list):
		frappe.throw(_("Select at least one time slot"))
	return slots


def _merge_contiguous_slots(slots):
	"""Coalesce back-to-back slots for the same facility and date into one
	continuous booking before anything is created - so a guest who picks
	"8-9" and "9-10" on the same court ends up with a single 8-10 Facility
	Booking (one check-in, one invoice line, one plain amount) instead of
	two separate bookings that only turn out to be related once you dig
	into their shared Sales Invoice. _get_invoice_group() (see
	get_booking_status()) still exists for the cases this can't collapse
	away - genuinely different facilities, non-adjacent times, or
	different dates picked in the same checkout - and keeps working
	exactly as before for those.

	Only merges slots that are truly adjacent: same sports_facility, same
	booking_date, and one's end_time exactly equal to the next one's
	start_time (compared via get_time(), not raw strings - same reason as
	every other time comparison in this file). A gap (e.g. "8-9" + "10-
	11") or a different facility never merges; each stays its own slot,
	same as before. Input order isn't assumed to be sorted or grouped -
	this does both before merging.
	"""
	groups = {}
	group_order = []
	for slot in slots:
		key = (slot.get("sports_facility"), str(slot.get("booking_date")))
		if key not in groups:
			groups[key] = []
			group_order.append(key)
		groups[key].append(slot)

	merged = []
	for key in group_order:
		ordered = sorted(groups[key], key=lambda s: get_time(s.get("start_time")))
		current = None
		for slot in ordered:
			if current is not None and get_time(current["end_time"]) == get_time(slot.get("start_time")):
				current["end_time"] = slot.get("end_time")
			else:
				if current is not None:
					merged.append(current)
				current = dict(slot)
		if current is not None:
			merged.append(current)
	return merged


def _new_cart_booking(customer, slot, notes=None, email=None, phone=None, guest_name=None):
	booking = frappe.new_doc("Facility Booking")
	booking.customer = customer
	booking.court = slot.get("sports_facility")
	booking.booking_date = slot.get("booking_date")
	booking.start_time = slot.get("start_time")
	booking.end_time = slot.get("end_time")
	# One note from the customer about this checkout, not per-slot - every
	# booking in the cart gets the same shared note. Same for email/phone/
	# guest_name - one contact for the whole checkout, not looked up per slot.
	booking.notes = notes
	booking.email = email
	booking.phone = phone
	booking.guest_name = guest_name
	booking.rate = frappe.get_cached_doc("Sports Facility", booking.court).get_effective_hourly_rate()
	# Tells on_submit() to skip creating (and the customer paying for) a
	# separate invoice for this one booking - _run_cart() below invoices
	# the whole cart together once every slot in it has submitted.
	booking.flags.cart_mode = True
	booking.insert(ignore_permissions=True)
	booking.submit()
	return booking


def _rollback_cart_bookings(bookings):
	"""Cancel every booking already submitted in this cart attempt.

	Facility Booking's naming series allocation commits the current
	transaction as a side effect of reserving each booking's name (the
	same behaviour documented on create_guest_booking() for Member) - so
	if slot 3 of 5 fails validation (already taken, past the per-day
	limit, whatever), slots 1 and 2 are already durably saved and won't
	be undone just because this request goes on to raise. Cancelling them
	explicitly avoids leaving the customer with a couple of "confirmed"
	bookings from a cart they never got to finish or pay for.
	"""
	for booking in bookings:
		try:
			booking.cancel()
		except Exception:
			frappe.log_error(
				title="Sports Complex: could not roll back cart booking",
				message=frappe.get_traceback(),
			)
	frappe.db.commit()


def _create_cart_invoice(customer, bookings):
	"""One Sales Invoice covering every booking in the cart - a line item
	per slot - so the customer pays once for the whole cart instead of
	once per slot. Mirrors create_sales_invoice()'s own Item-resolution
	rules (per-facility Billing Item, falling back to a same-named
	Facility Type Item) rather than duplicating them differently here.
	"""
	items = []
	for booking in bookings:
		facility_type, billing_item = frappe.db.get_value(
			"Sports Facility", booking.court, ["facility_type", "billing_item"]
		)
		item_code = billing_item or facility_type
		if not item_code or not frappe.db.exists("Item", item_code):
			frappe.throw(
				_(
					"No billing Item configured for facility {0}. Set a Billing Item on the "
					"Sports Facility (or create a sellable Item named {1}) before confirming "
					"bookings."
				).format(booking.court, facility_type or "")
			)
		items.append({"item_code": item_code, "qty": 1, "rate": booking.total_amount or booking.rate or 0})

	si = frappe.new_doc("Sales Invoice")
	si.customer = customer
	# Only the first booking gets this forward link - the generic
	# SOURCE_MAP hook in utils/paystack_hooks.py only needs it to notice
	# "this invoice is a Facility Booking invoice" at all; it then
	# resolves every booking actually tied to this invoice via a reverse
	# lookup on Facility Booking.sales_invoice, not from this field alone
	# - see that module's on_payment_authorized().
	si.facility_booking = bookings[0].name
	for item in items:
		si.append("items", item)
	si.flags.ignore_permissions = True
	si.insert()
	si.submit()

	for booking in bookings:
		booking.db_set("sales_invoice", si.name)

	return si


def _finalize_cart_bookings(bookings):
	settings = frappe.get_cached_doc("Sports Complex Setup")
	status = (
		"Payment Pending"
		if cint(settings.enable_paystack_payments) and cint(settings.require_payment_before_confirmation)
		else "Confirmed"
	)
	for booking in bookings:
		booking.db_set("booking_status", status)
		if status == "Confirmed":
			sync_booking_to_calendar(booking)
	return status


def _run_cart(customer, slots, notes=None, email=None, phone=None, guest_name=None):
	"""Shared pipeline behind create_booking_cart() and create_guest_
	booking_cart(): submit one booking per slot (same validate() chain a
	single booking goes through), bill them all on one shared Sales
	Invoice, and settle their booking_status together - rolling every
	booking from this attempt back if any step along the way fails,
	rather than leaving a partial, unpaid, unconfirmed cart behind.

	Back-to-back slots for the same facility/date are merged into one
	continuous booking first - see _merge_contiguous_slots() - so this
	only ever creates as many Facility Bookings as there are actual
	distinct visits, not one per fixed-duration slot the guest happened
	to click.
	"""
	slots = _merge_contiguous_slots(slots)
	bookings = []
	try:
		for slot in slots:
			bookings.append(
				_new_cart_booking(customer, slot, notes=notes, email=email, phone=phone, guest_name=guest_name)
			)
		_create_cart_invoice(customer, bookings)
		status = _finalize_cart_bookings(bookings)
	except Exception:
		_rollback_cart_bookings(bookings)
		raise
	return bookings, status


@frappe.whitelist()
def create_staff_booking_cart(customer, slots, notes=None):
	"""Cart counterpart to create_staff_booking(): lets staff on the
	Facility Check-In board book several time slots for one walk-in/phone
	customer in a single visit - same facility, back-to-back or spaced
	out across the day - billed together on one Sales Invoice, exactly
	like create_booking_cart() does for a customer checking themselves
	out through /book-facility. See _run_cart() for the shared submit-
	all/one-invoice/rollback-on-failure pipeline, and
	_merge_contiguous_slots() for why picking "9-10" and "10-11" back to
	back lands as a single 9-11 Facility Booking rather than two.

	slots: list of {"sports_facility", "booking_date", "start_time",
	"end_time"} dicts, one per selected slot - same shape
	create_booking_cart() takes, just gathered from the check-in board's
	own slot picker instead of the public booking page's cart.

	There used to be a mark_paid flag here (a "Payment Collected"
	checkbox on the Book Facility dialog, staff attesting cash/card was
	already taken at the desk) that called
	FacilityBooking.mark_paid_and_confirm() directly on every booking in
	the cart. That method only flips the booking's own
	payment_status/booking_status fields - it never touches the Sales
	Invoice this cart just created, since every other caller of it
	(Paystack's webhook in utils/paystack_hooks.py, Cashier's
	create_facility_payment_entry()) only ever calls it *after* a real
	Payment Entry has already settled the invoice. Calling it here with
	no Payment Entry in between left the booking reading "Confirmed /
	Paid" while its invoice sat "Unpaid" with no financial record of the
	cash collected. A booking made here that's actually been paid for in
	person should have that payment collected through the Cashier page
	instead (page/cashier/cashier.py's create_facility_payment_entry()),
	which creates and submits the Payment Entry first.
	"""
	if not _is_booking_staff():
		frappe.throw(_("Not permitted to book on behalf of a customer"), frappe.PermissionError)

	if not frappe.db.exists("Customer", customer):
		frappe.throw(_("Customer {0} not found").format(customer))

	email, phone = _resolve_member_contact(customer)

	slots = _parse_slots(slots)
	bookings, status = _run_cart(customer, slots, notes=notes, email=email, phone=phone)

	_send_booking_confirmation_email(email, bookings)

	return {
		"bookings": [b.name for b in bookings],
		"booking_status": status,
	}


@frappe.whitelist()
def create_booking_cart(slots, notes=None):
	"""Cart counterpart to create_booking(): book several time slots for a
	logged-in customer in one go, paid for together as a single Sales
	Invoice / single Paystack checkout - see _run_cart().

	slots: list of {"sports_facility", "booking_date", "start_time",
	"end_time"} dicts, one per selected slot.
	"""
	customer = resolve_session_customer()
	if not customer:
		frappe.throw(
			_("No Customer record is linked to your account. Contact the front desk to book."),
			frappe.PermissionError,
		)

	email, phone = _resolve_member_contact(customer)

	slots = _parse_slots(slots)
	bookings, status = _run_cart(customer, slots, notes=notes, email=email, phone=phone)

	_send_booking_confirmation_email(email, bookings)

	result = {
		"bookings": [{"name": b.name, "token": None} for b in bookings],
		"booking_status": status,
	}
	if status == "Payment Pending":
		result["payment_link"] = get_booking_payment_link(bookings[0].name)
	return result


@frappe.whitelist(allow_guest=True)
def get_booking_payment_link(facility_booking, token=None):
	"""Return a Paystack checkout URL for this booking's Sales Invoice.
	Delegates to frappe_paystack's own create_payment_link() (the same
	generic helper every other checkout flow in this codebase already
	uses) instead of duplicating its Paystack-settings/currency
	resolution here. allow_guest=True so a guest booking's own access
	token (see get_booking_access_token) is enough to pay - _ensure_
	booking_access still enforces that it's *this* booking's token.

	Refuses once booking_status has moved off Payment Pending - a guest
	who still has an old "Pay Now" tab or link open from before the
	booking auto-cancelled (see auto_cancel_unpaid_bookings()) or
	otherwise changed state would previously still reach a working
	checkout for it. Checked here as well as by voiding the invoice on
	auto-cancel, since this also covers every other way booking_status
	can move on (manual cancellation, a staff override, a future path
	this doesn't know about yet) - not just the auto-cancel job.
	"""
	booking = frappe.get_doc("Facility Booking", facility_booking)
	_ensure_booking_access(booking, resolve_session_customer(), token)

	if booking.booking_status != "Payment Pending":
		frappe.throw(
			_("This booking is no longer awaiting payment (status: {0}) - a new payment link can't be issued.").format(
				booking.booking_status
			)
		)

	if not booking.sales_invoice:
		frappe.throw(_("This booking has no invoice yet - submit it first"))

	from frappe_paystack.api import create_payment_link

	return create_payment_link("Sales Invoice", booking.sales_invoice)


@frappe.whitelist(allow_guest=True)
def list_bookable_facilities():
	"""Sports Facility's own desk permissions (Facility Manager / Front
	Desk / System Manager only - a separate role set from Facility
	Booking's own Sports Complex Manager/Staff, worth reconciling
	separately) don't include Guest or Customer, so a self-service
	booking page can't just frappe.call frappe.client.get_list against
	Sports Facility directly. This is the read-only, guest-safe
	equivalent - enough to populate a public grid of bookable facilities
	(image, price, today's availability).

	Renamed from list_bookable_courts() / the old Court doctype: a
	facility used to have one or more Court "units" under it, but in
	practice every facility only ever had exactly one, so Sports Facility
	is now the bookable unit itself - see
	sports_complex/patches/remove_court_doctype.py.
	"""
	facilities = frappe.get_all(
		"Sports Facility",
		filters={"status": "Active"},
		fields=["name", "facility_name", "facility_type", "surface_type", "hourly_rate", "image", "amenities"],
		order_by="facility_name asc",
	)

	today = nowdate()
	for f in facilities:
		f["hourly_rate"] = f.hourly_rate or frappe.get_cached_doc("Sports Facility", f.name).get_effective_hourly_rate()
		# Real, date-specific availability rather than a static status
		# field - reuses get_available_slots so the grid's badge and the
		# slot picker behind it can never disagree.
		f["open_slots_today"] = len(get_available_slots(f.name, today))

	return facilities


@frappe.whitelist(allow_guest=True, methods=["POST"])
def create_guest_booking(
	sports_facility, booking_date, start_time, end_time, email, otp=None, full_name=None,
	phone=None, notes=None, remember_token=None
):
	"""Guest counterpart to create_booking(): verifies the emailed OTP,
	resolves (or creates) a Member/Customer for that email, then runs the
	booking through the exact same validate() chain create_booking()
	does. Returns an HMAC access token instead of relying on a session,
	since this caller was never logged in and never will be for this
	booking - see get_booking_access_token.

	Member's autoname is Naming Series based, and Frappe's naming-series
	counter allocation (frappe.model.naming.getseries) commits the
	current transaction as a side effect of reserving the next number -
	so a brand-new guest's Member/Customer created here is durably saved
	the moment resolve_or_create_guest_customer() returns, regardless of
	whether the booking itself goes on to fail. Without the try/except
	below, every failed guest booking attempt (bad slot, race with
	another booking, whatever) would silently leave behind an orphaned
	Customer - which is exactly what was happening (repeated failed
	attempts from the same email produced "Rita Boadu", "Rita Boadu -
	1", ...). If the booking fails and we created the customer in this
	same call, we delete it again rather than leave it behind; an
	already-existing customer for this email is never touched.

	remember_token, when it verifies (see guest_booking.
	verify_booking_remember_token), stands in for otp entirely - a guest
	who already typed a correct code once within the last
	BOOKING_REMEMBER_TOKEN_TTL_SECONDS doesn't need to fetch and retype
	another one for a second booking in the same sitting. Either way, a
	fresh remember_token covering the same window from now is handed back
	in the result, sliding the window forward on every successful booking
	rather than the guest hitting a hard wall exactly N minutes after the
	one time they entered a code.
	"""
	from sports_complex.utils.guest_booking import (
		issue_booking_remember_token,
		resolve_or_create_guest_customer,
		verify_booking_otp,
		verify_booking_remember_token,
	)

	normalized_email = (email or "").strip().lower()
	if not (remember_token and verify_booking_remember_token(normalized_email, remember_token)):
		verify_booking_otp(email, otp)

	pre_existing_customer = frappe.db.get_value("Member", {"email": normalized_email}, "customer")

	# resolve_or_create_guest_customer() already elevates to Administrator
	# for its own Member/Customer creation (see its docstring), but that
	# elevation ends the moment it returns. booking.submit() below fires
	# on_submit() -> create_sales_invoice(), and ERPNext's own Sales
	# Invoice controller touches/creates a Contact too (the same class of
	# ERPNext-internal side effect, just a second, later occurrence of it)
	# - which was 403ing again for Guest even after the first Contact
	# error was fixed, because by then the earlier elevation had already
	# been restored back to Guest. Elevating around this whole block too
	# closes that off without needing to know exactly which ERPNext
	# controller does it.
	original_user = frappe.session.user
	frappe.set_user("Administrator")
	try:
		customer = resolve_or_create_guest_customer(email, full_name, phone)
		customer_created_here = not pre_existing_customer
		# guest_name records who actually typed *this* booking, independent
		# of the shared Customer's own name (see resolve_or_create_guest_
		# customer's docstring) - falls back to the Customer's current name
		# only for the rare case full_name arrived blank (e.g. a client
		# bug), so the field is never left empty when a name is already
		# known.
		guest_name = (full_name or "").strip() or frappe.db.get_value("Customer", customer, "customer_name")

		try:
			booking = frappe.new_doc("Facility Booking")
			booking.customer = customer
			booking.court = sports_facility
			booking.booking_date = booking_date
			booking.start_time = start_time
			booking.end_time = end_time
			booking.notes = notes
			booking.email = normalized_email
			booking.phone = phone
			booking.guest_name = guest_name
			booking.rate = frappe.get_cached_doc("Sports Facility", sports_facility).get_effective_hourly_rate()
			booking.insert(ignore_permissions=True)
			booking.submit()
		except Exception:
			if customer_created_here:
				_delete_orphaned_guest_customer(customer)
			raise
	finally:
		frappe.set_user(original_user)

	token = get_booking_access_token(booking.name)
	_send_booking_confirmation_email(email, [booking], tokens={booking.name: token})

	result = {
		"booking": booking.name,
		"booking_status": booking.booking_status,
		"token": token,
		"remember_token": issue_booking_remember_token(normalized_email),
	}
	if booking.booking_status == "Payment Pending":
		result["payment_link"] = get_booking_payment_link(booking.name, token=token)
	return result


@frappe.whitelist(allow_guest=True, methods=["POST"])
def create_guest_booking_cart(slots, email, otp=None, full_name=None, phone=None, notes=None, remember_token=None):
	"""Guest counterpart to create_booking_cart(): same email-OTP identity
	check and the same Administrator elevation, for the same reasons, as
	create_guest_booking() - just wrapping a whole cart of bookings and
	their one shared invoice (_run_cart()) instead of a single booking and
	its own invoice.

	remember_token can stand in for otp here too - see the note on
	create_guest_booking() above; the same short-lived, slide-forward
	token works across both entry points since they identify the guest by
	the same email either way.
	"""
	from sports_complex.utils.guest_booking import (
		issue_booking_remember_token,
		resolve_or_create_guest_customer,
		verify_booking_otp,
		verify_booking_remember_token,
	)

	normalized_email = (email or "").strip().lower()
	if not (remember_token and verify_booking_remember_token(normalized_email, remember_token)):
		verify_booking_otp(email, otp)
	slots = _parse_slots(slots)

	pre_existing_customer = frappe.db.get_value("Member", {"email": normalized_email}, "customer")

	original_user = frappe.session.user
	frappe.set_user("Administrator")
	try:
		customer = resolve_or_create_guest_customer(email, full_name, phone)
		customer_created_here = not pre_existing_customer
		guest_name = (full_name or "").strip() or frappe.db.get_value("Customer", customer, "customer_name")

		try:
			bookings, status = _run_cart(
				customer, slots, notes=notes, email=normalized_email, phone=phone, guest_name=guest_name
			)
		except Exception:
			if customer_created_here:
				_delete_orphaned_guest_customer(customer)
			raise
	finally:
		frappe.set_user(original_user)

	bookings_out = [{"name": b.name, "token": get_booking_access_token(b.name)} for b in bookings]
	_send_booking_confirmation_email(
		email, bookings, tokens={b["name"]: b["token"] for b in bookings_out}
	)

	result = {
		"bookings": bookings_out,
		"booking_status": status,
		"remember_token": issue_booking_remember_token(normalized_email),
	}
	if status == "Payment Pending":
		result["payment_link"] = get_booking_payment_link(bookings[0].name, token=bookings_out[0]["token"])
	return result


def _delete_orphaned_guest_customer(customer):
	"""Best-effort cleanup for create_guest_booking(): delete a Customer
	(and its linked Member) that was only just created for a booking
	attempt that then failed. Failures here are logged, not raised - the
	booking's own error is what the caller needs to see, and a customer
	that couldn't be cleaned up is a cosmetic leftover, not worth masking
	the real error over.
	"""
	try:
		member_name = frappe.db.get_value("Member", {"customer": customer}, "name")
		if member_name:
			frappe.delete_doc("Member", member_name, ignore_permissions=True, force=True)
		if frappe.db.exists("Customer", customer):
			frappe.delete_doc("Customer", customer, ignore_permissions=True, force=True)
		frappe.db.commit()
	except Exception:
		frappe.log_error(
			title="Sports Complex: could not clean up orphaned guest customer",
			message=frappe.get_traceback(),
		)


def _get_venue_map(sports_facility_names):
	"""Batch-resolve each Sports Facility's Venue (name/address/city/lat/lon)
	in two queries total, regardless of how many bookings/facilities are
	passed in - avoids an N+1 query per booking row on list_my_bookings.

	Returns {sports_facility_name: {venue_name, address, city, lat, lon}}.
	A facility with no Venue linked (or a Venue with no pin dropped yet)
	still gets an entry, just with None values, so callers can merge
	unconditionally without a membership check.
	"""
	sports_facility_names = list({n for n in sports_facility_names if n})
	if not sports_facility_names:
		return {}

	facility_venues = frappe.get_all(
		"Sports Facility",
		filters={"name": ["in", sports_facility_names]},
		fields=["name", "venue"],
	)
	venue_names = list({f.venue for f in facility_venues if f.venue})

	venues = {}
	if venue_names:
		for v in frappe.get_all(
			"Venue",
			filters={"name": ["in", venue_names]},
			fields=["name", "venue_name", "address", "city", "location"],
		):
			lat = lon = None
			if v.location:
				# Geolocation fields store a GeoJSON FeatureCollection string;
				# coordinates are [longitude, latitude] per the GeoJSON spec,
				# the reverse of the usual lat/lon speaking order - see the
				# geojson construction in venue.js for the matching write side.
				try:
					coords = json.loads(v.location)["features"][0]["geometry"]["coordinates"]
					lon, lat = coords[0], coords[1]
				except (ValueError, KeyError, IndexError, TypeError):
					pass
			venues[v.name] = {
				"venue_name": v.venue_name,
				"address": v.address,
				"city": v.city,
				"lat": lat,
				"lon": lon,
			}

	empty = {"venue_name": None, "address": None, "city": None, "lat": None, "lon": None}
	return {f.name: venues.get(f.venue, empty) for f in facility_venues}


def _get_invoice_group(booking):
	"""When this booking was created as part of a multi-slot cart (see
	_run_cart()), every booking in that cart shares one Sales Invoice, and
	Pay Now/get_booking_payment_link() settles that invoice's full
	grand_total - not just this one booking's own total_amount. Showing
	only total_amount on the confirmation page was misleading: a guest
	opening one 350 booking's own page could land on a Paystack checkout
	billing 700, because the other slot they added to the same cart was
	invoiced together with it.

	Returns (amount_actually_due, sibling_bookings) - amount_actually_due
	is the invoice's real grand_total when one exists (falling back to
	this booking's own total_amount for a booking with no invoice yet, or
	one that was never part of a cart), and sibling_bookings is every
	other booking sharing that same invoice, formatted the same way
	list_my_bookings() formats its rows, empty unless there's actually
	more than one - a lone booking doesn't need a breakdown of itself.
	"""
	if not booking.sales_invoice:
		return booking.total_amount, []

	invoice_total = frappe.db.get_value("Sales Invoice", booking.sales_invoice, "grand_total")

	siblings = frappe.get_all(
		"Facility Booking",
		filters={"sales_invoice": booking.sales_invoice},
		fields=["name", "court", "booking_date", "start_time", "end_time", "total_amount"],
		order_by="booking_date asc, start_time asc",
	)
	if len(siblings) <= 1:
		return booking.total_amount, []

	facility_names = list({s.court for s in siblings if s.court})
	facility_labels = dict(frappe.get_all(
		"Sports Facility",
		filters={"name": ["in", facility_names]},
		fields=["name", "facility_name"],
		as_list=True,
	)) if facility_names else {}

	for s in siblings:
		s["facility_name"] = facility_labels.get(s.court) or s.court
		s["booking_date"] = str(s.booking_date) if s.booking_date else None
		s["start_time"] = str(s.start_time) if s.start_time else None
		s["end_time"] = str(s.end_time) if s.end_time else None

	return (flt(invoice_total) or booking.total_amount), siblings


def _get_cancellation_reasons(booking_names):
	"""Map of facility_booking name -> its most recent submitted Booking
	Cancellation's reason, for every name in booking_names that actually
	has one. BookingCancellation.on_submit() is what flips booking_status
	to "Cancelled" in the first place (a frappe.db.set_value there, not a
	real docstatus-level cancel of the Facility Booking itself - see its
	own comment) - a guest looking at a Cancelled booking never had
	anywhere to see *why*, since that reason only ever lived on this
	separate, desk-only doctype. Surfaced here the same way no_show_
	penalty_amount only shows once a booking reaches No-show - see
	get_booking_status()/list_my_bookings().

	Batched (one query for every name that might need one) rather than
	called per-booking, so list_my_bookings() doesn't run N extra queries
	for a guest with N cancelled bookings.
	"""
	if not booking_names:
		return {}
	rows = frappe.get_all(
		"Booking Cancellation",
		filters={"facility_booking": ["in", booking_names], "docstatus": 1},
		fields=["facility_booking", "reason"],
		order_by="cancellation_date desc, creation desc",
	)
	reasons = {}
	for row in rows:
		# order_by already puts the most recent first per booking - the
		# first one seen here wins, covering the (unlikely but possible)
		# case of more than one submitted cancellation against the same
		# booking.
		reasons.setdefault(row.facility_booking, row.reason)
	return reasons


@frappe.whitelist(allow_guest=True)
def get_booking_status(facility_booking, token=None):
	"""Feed the booking confirmation/status page - works for a logged-in
	customer (session ownership), a guest with their access token, or
	staff, via the same _ensure_booking_access check every other guest-
	reachable method here uses.
	"""
	booking = frappe.get_doc("Facility Booking", facility_booking)
	_ensure_booking_access(booking, resolve_session_customer(), token)

	venue = _get_venue_map([booking.court]).get(booking.court, {})
	invoice_amount, cart_bookings = _get_invoice_group(booking)
	cancellation_reason = None
	if booking.booking_status == "Cancelled":
		cancellation_reason = _get_cancellation_reasons([booking.name]).get(booking.name)

	return {
		"name": booking.name,
		"sports_facility": booking.court,
		"booking_date": str(booking.booking_date) if booking.booking_date else None,
		"start_time": str(booking.start_time) if booking.start_time else None,
		"end_time": str(booking.end_time) if booking.end_time else None,
		"booking_status": booking.booking_status,
		"payment_status": booking.payment_status,
		"total_amount": booking.total_amount,
		"invoice_amount": invoice_amount,
		"cart_bookings": cart_bookings,
		"no_show_penalty_amount": booking.no_show_penalty_amount,
		"cancellation_reason": cancellation_reason,
		"sales_invoice": booking.sales_invoice,
		"venue_name": venue.get("venue_name"),
		"venue_address": venue.get("address"),
		"venue_city": venue.get("city"),
		"venue_lat": venue.get("lat"),
		"venue_lon": venue.get("lon"),
	}


@frappe.whitelist(allow_guest=True)
def list_my_bookings(email=None, otp=None, remember_token=None):
	"""Feed a self-service "My Bookings" page.

	A logged-in customer needs no extra proof - resolve_session_customer()
	already ties their session to a Customer, the same identity every
	other guest-reachable method here trusts. A guest has no session
	identity to check, so they have to prove ownership of the email
	address the same way create_guest_booking() does: by verifying a
	one-time code just sent to it (send_booking_otp/verify_booking_otp) -
	unless remember_token already proves it, a signed token issued the
	last time this same guest verified an OTP here (see
	issue_my_bookings_remember_token) and stored client-side, so a
	returning guest within the remember window doesn't have to request
	and retype a fresh code every visit.

	Returns {"bookings": [...], "remember_token": ..., "verified": ...,
	"customer_name": ...} rather than a bare list - remember_token is a
	freshly (re)issued token for the guest path (sliding the window
	forward on every successful visit), or None when there was no guest
	identity to remember (a logged-in customer's session already covers
	that). customer_name is the Customer record's own display name,
	fetched once here and reused for both the guest and logged-in paths -
	see the my-bookings header, which shows it once bookings are loaded.
	verified is False
	only for the one case that isn't something the guest actively did
	this visit: a remembered token that turned out to be missing,
	expired, or tampered with, and no OTP supplied alongside it to fall
	back on - see tryRememberedLogin() in my-bookings' index.js, which
	relies on this NOT raising so that automatic background check can
	fall back to the normal email/OTP form without popping an error
	dialog the guest never asked for. Every other path either succeeds
	(verified: True) or frappe.throw()s as before, since those happen in
	response to something the guest actively did and should surface if
	something's wrong.
	"""
	customer = resolve_session_customer()
	fresh_remember_token = None

	if not customer:
		if frappe.session.user and frappe.session.user != "Guest":
			frappe.throw(_("No Customer record is linked to your account. Contact the front desk for help."))

		from sports_complex.utils.guest_booking import (
			issue_my_bookings_remember_token,
			verify_booking_otp,
			verify_my_bookings_remember_token,
		)

		if email and remember_token and verify_my_bookings_remember_token(email, remember_token):
			pass
		elif email and otp:
			verify_booking_otp(email, otp)
		elif remember_token:
			return {"bookings": [], "remember_token": None, "verified": False}
		else:
			frappe.throw(_("Enter your email and verification code to view your bookings"))

		normalized_email = (email or "").strip().lower()
		customer = frappe.db.get_value("Member", {"email": normalized_email}, "customer")
		if not customer:
			return {"bookings": [], "remember_token": None, "verified": True}

		fresh_remember_token = issue_my_bookings_remember_token(normalized_email)

	customer_name = frappe.db.get_value("Customer", customer, "customer_name")

	bookings = frappe.get_all(
		"Facility Booking",
		filters={"customer": customer},
		fields=[
			"name", "court", "booking_date", "start_time", "end_time",
			"booking_status", "payment_status", "total_amount", "no_show_penalty_amount",
		],
		order_by="booking_date desc, start_time desc",
	)

	facility_names = list({b.court for b in bookings if b.court})
	facility_labels = dict(frappe.get_all(
		"Sports Facility",
		filters={"name": ["in", facility_names]},
		fields=["name", "facility_name"],
		as_list=True,
	)) if facility_names else {}
	venue_map = _get_venue_map(facility_names)
	cancellation_reasons = _get_cancellation_reasons(
		[b.name for b in bookings if b.booking_status == "Cancelled"]
	)

	for b in bookings:
		b["facility_name"] = facility_labels.get(b.court) or b.court
		b["booking_date"] = str(b.booking_date) if b.booking_date else None
		b["start_time"] = str(b.start_time) if b.start_time else None
		b["end_time"] = str(b.end_time) if b.end_time else None
		b["cancellation_reason"] = cancellation_reasons.get(b.name)
		# A guest still needs the same signed access token to open any one
		# booking's own confirmation/pay/cancel page - this list is not
		# itself proof of ownership of an individual booking name.
		b["token"] = get_booking_access_token(b.name)

		venue = venue_map.get(b.court, {})
		b["venue_name"] = venue.get("venue_name")
		b["venue_address"] = venue.get("address")
		b["venue_city"] = venue.get("city")
		b["venue_lat"] = venue.get("lat")
		b["venue_lon"] = venue.get("lon")

	return {
		"bookings": bookings,
		"remember_token": fresh_remember_token,
		"verified": True,
		"customer_name": customer_name,
	}


@frappe.whitelist(allow_guest=True, methods=["POST"])
def request_cancellation(facility_booking, token=None, reason=None):
	"""Self-service cancellation for a logged-in customer or a guest with
	a valid access token. Booking Cancellation's own validate() already
	enforces the Cancellation Window (Hours) setting (see
	booking_cancellation.py) - this just supplies the ownership check
	that doctype's desk-only permissions don't, the same way create_
	booking()/create_guest_booking() do for Facility Booking itself.
	"""
	booking = frappe.get_doc("Facility Booking", facility_booking)
	_ensure_booking_access(booking, resolve_session_customer(), token)

	cancellation = frappe.new_doc("Booking Cancellation")
	cancellation.facility_booking = booking.name
	cancellation.reason = reason
	cancellation.flags.ignore_permissions = True
	cancellation.insert()
	cancellation.submit()
	return {"cancelled": True}