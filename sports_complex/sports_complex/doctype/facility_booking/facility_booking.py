# Copyright (c) 2026, Your Company and contributors
# For license information, please see license.txt

import hashlib
import hmac
from datetime import timedelta

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, get_datetime, now_datetime, time_diff_in_hours
from frappe.utils.password import get_encryption_key

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
		if self.start_time and self.end_time and self.start_time >= self.end_time:
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

		# Lock the Court row for the rest of this transaction so two
		# near-simultaneous submissions for the same court can't both read
		# "no conflict" here before either has actually committed - a
		# classic check-then-act race. Without this, two customers hitting
		# create_booking() for the same slot at the same moment could both
		# pass this check and end up with two confirmed bookings for one
		# court.
		frappe.db.sql("select name from `tabCourt` where name=%s for update", (self.court,))

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
		if not (self.court and self.booking_date and self.start_time and self.end_time):
			return

		sports_facility = frappe.db.get_value("Court", self.court, "sports_facility")

		conflicting = frappe.db.sql(
			"""
			select name
			from `tabMaintenance Schedule`
			where (court = %(court)s or sports_facility = %(sports_facility)s)
				and scheduled_date = %(booking_date)s
				and docstatus = 1
				and status != 'Completed'
				and (
					scheduled_start is null
					or scheduled_end is null
					or (scheduled_start < %(end_time)s and scheduled_end > %(start_time)s)
				)
			limit 1
			""",
			{
				"court": self.court,
				"sports_facility": sports_facility,
				"booking_date": self.booking_date,
				"start_time": self.start_time,
				"end_time": self.end_time,
			},
		)
		if conflicting:
			frappe.throw(
				_("Court {0} has scheduled maintenance overlapping this time on {1} ({2})").format(
					self.court, self.booking_date, conflicting[0][0]
				)
			)

	def on_submit(self):
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

	def on_cancel(self):
		self.db_set("booking_status", "Cancelled")

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

	def create_sales_invoice(self):
		"""Create the linked Sales Invoice that frappe_paystack will take payment against.

		NOTE: this assumes:
		1. Sales Invoice has a custom Link field `facility_booking` (see schema
		   doc section 6 — add via Customize Form or a fixtures JSON).
		2. There is a sellable Item to bill against. For now this looks for an
		   Item named after the Court's Facility Type; adjust once Sports
		   Settings has a proper Item mapping field.
		"""
		if self.sales_invoice:
			return

		facility_type = frappe.db.get_value(
			"Sports Facility",
			frappe.db.get_value("Court", self.court, "sports_facility"),
			"facility_type",
		)

		if not facility_type or not frappe.db.exists("Item", facility_type):
			frappe.throw(
				_(
					"No Item found for Facility Type {0}. Create a sellable Item with that "
					"name (or update create_sales_invoice) before confirming bookings."
				).format(facility_type or "")
			)

		si = frappe.new_doc("Sales Invoice")
		si.customer = self.customer
		si.facility_booking = self.name
		si.append(
			"items",
			{
				"item_code": facility_type,
				"qty": 1,
				"rate": self.total_amount or self.rate or 0,
			},
		)
		si.flags.ignore_permissions = True
		si.insert()

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
def get_available_slots(court, date):
	"""List the open time ranges for a court on a given date: each active
	Booking Schedule slot for that court/day-of-week, minus whatever's
	already booked (Facility Booking) or under maintenance (Maintenance
	Schedule), keeping Sports Complex Setup's Buffer Time Between Bookings
	clear around each busy interval.

	This is the "can I book this?" counterpart to the buzz app's
	Event Ticket Type.remaining_tickets - see BOOKING_RECOMMENDATIONS.md.
	allow_guest=True because this is read-only availability info, not a
	booking action - browsing what's open shouldn't require logging in.
	"""
	day_of_week = get_datetime(date).strftime("%A")

	template_slots = frappe.get_all(
		"Booking Schedule",
		filters={"court": court, "day_of_week": day_of_week, "is_active": 1},
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
			"court": court,
			"booking_date": date,
			"docstatus": ("<", 2),
			"booking_status": ("not in", ["Cancelled", "No-show"]),
		},
		fields=["start_time", "end_time"],
	):
		busy.append(_padded(row.start_time, row.end_time, buffer_minutes))

	for row in frappe.get_all(
		"Maintenance Schedule",
		filters={
			"court": court,
			"scheduled_date": date,
			"docstatus": 1,
			"status": ("!=", "Completed"),
		},
		fields=["scheduled_start", "scheduled_end"],
	):
		if row.scheduled_start and row.scheduled_end:
			busy.append((row.scheduled_start, row.scheduled_end))

	slots = []
	for template in template_slots:
		for free_start, free_end in _subtract_busy(template.slot_start, template.slot_end, busy):
			slots.append(
				{
					"start_time": str(free_start),
					"end_time": str(free_end),
					"slot_duration": template.slot_duration,
				}
			)
	return slots


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


@frappe.whitelist()
def create_booking(court, booking_date, start_time, end_time):
	"""Self-service entry point for a logged-in member/customer to book a
	court themselves. Runs the exact same validate() chain a staff-created
	booking goes through (overlap, maintenance, schedule, notice-window,
	per-day limit) - ignore_permissions only bypasses Facility Booking's
	desk-only create/submit permissions, which is what this whitelisted
	method's own ownership check (resolve_session_customer requiring a
	real, logged-in Customer) exists to replace.

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

	booking = frappe.new_doc("Facility Booking")
	booking.customer = customer
	booking.court = court
	booking.booking_date = booking_date
	booking.start_time = start_time
	booking.end_time = end_time
	booking.rate = frappe.get_cached_doc("Court", court).get_effective_hourly_rate()
	booking.flags.ignore_permissions = True
	booking.insert()
	booking.submit()

	result = {"booking": booking.name, "booking_status": booking.booking_status}
	if booking.booking_status == "Payment Pending":
		result["payment_link"] = get_booking_payment_link(booking.name)
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
	"""
	booking = frappe.get_doc("Facility Booking", facility_booking)
	_ensure_booking_access(booking, resolve_session_customer(), token)

	if not booking.sales_invoice:
		frappe.throw(_("This booking has no invoice yet - submit it first"))

	from frappe_paystack.api import create_payment_link

	return create_payment_link("Sales Invoice", booking.sales_invoice)


@frappe.whitelist(allow_guest=True)
def list_bookable_courts():
	"""Court's own desk permissions (Facility Manager / Front Desk /
	System Manager only - a separate role set from Facility Booking's
	own Sports Complex Manager/Staff, worth reconciling separately) don't
	include Guest or Customer, so a self-service booking page can't just
	frappe.call frappe.client.get_list against Court directly. This is
	the read-only, guest-safe equivalent - just enough to populate a
	booking page's court picker.
	"""
	return frappe.get_all(
		"Court",
		filters={"status": ("!=", "Maintenance")},
		fields=["name", "sports_facility", "court_number", "surface_type"],
		order_by="sports_facility asc, court_number asc",
	)


@frappe.whitelist(allow_guest=True, methods=["POST"])
def create_guest_booking(court, booking_date, start_time, end_time, email, otp, full_name, phone=None):
	"""Guest counterpart to create_booking(): verifies the emailed OTP,
	resolves (or creates) a Member/Customer for that email, then runs the
	booking through the exact same validate() chain create_booking()
	does. Returns an HMAC access token instead of relying on a session,
	since this caller was never logged in and never will be for this
	booking - see get_booking_access_token.
	"""
	from sports_complex.utils.guest_booking import (
		resolve_or_create_guest_customer,
		verify_booking_otp,
	)

	verify_booking_otp(email, otp)
	customer = resolve_or_create_guest_customer(email, full_name, phone)

	booking = frappe.new_doc("Facility Booking")
	booking.customer = customer
	booking.court = court
	booking.booking_date = booking_date
	booking.start_time = start_time
	booking.end_time = end_time
	booking.rate = frappe.get_cached_doc("Court", court).get_effective_hourly_rate()
	booking.flags.ignore_permissions = True
	booking.insert()
	booking.submit()

	token = get_booking_access_token(booking.name)
	result = {"booking": booking.name, "booking_status": booking.booking_status, "token": token}
	if booking.booking_status == "Payment Pending":
		result["payment_link"] = get_booking_payment_link(booking.name, token=token)
	return result


@frappe.whitelist(allow_guest=True)
def get_booking_status(facility_booking, token=None):
	"""Feed the booking confirmation/status page - works for a logged-in
	customer (session ownership), a guest with their access token, or
	staff, via the same _ensure_booking_access check every other guest-
	reachable method here uses.
	"""
	booking = frappe.get_doc("Facility Booking", facility_booking)
	_ensure_booking_access(booking, resolve_session_customer(), token)

	return {
		"name": booking.name,
		"court": booking.court,
		"booking_date": str(booking.booking_date) if booking.booking_date else None,
		"start_time": str(booking.start_time) if booking.start_time else None,
		"end_time": str(booking.end_time) if booking.end_time else None,
		"booking_status": booking.booking_status,
		"payment_status": booking.payment_status,
		"total_amount": booking.total_amount,
		"sales_invoice": booking.sales_invoice,
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