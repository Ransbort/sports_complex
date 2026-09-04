# Copyright (c) 2026, Sports Complex and contributors
# For license information, please see license.txt

"""Player Session - a private/1-on-1 booking with a roster Player, distinct
from Training Session (a coaching session with a Coach). Kept as its own
doctype rather than folded into Training Session: the two have different
shapes (one fixed participant here vs. a participants table there) and
different rules going forward (a Player's own guardian/medical concerns
live on the Player record, not a Coach's), so mixing them into one
doctype would mean branching on "is this a coach or a player row"
everywhere Training Session is used today.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, get_datetime, nowdate, time_diff_in_hours

from sports_complex.utils import cancel_linked_invoice, get_member_customer, make_linked_sales_invoice


class PlayerSession(Document):
	def validate(self):
		self.validate_court_conflict()
		self.set_total_amount()

	def validate_court_conflict(self):
		"""Same shape as TrainingSession.validate_court_conflict() - a Player
		Session consumes a court slot too, so it needs to check against
		everything already competing for that same court/date/time: Facility
		Booking, Maintenance Schedule, Training Session, and other Player
		Session rows. Deliberately one-directional, same as Training
		Session's own check: Facility Booking's own conflict check doesn't
		look at Training Session either, so nothing here retroactively
		changes what already-working flow validates against - this just
		makes sure a *new* Player Session never lands on a slot one of
		those already claims.
		"""
		if not (self.court and self.date and self.start_time and self.end_time):
			return

		booking_conflict = frappe.db.sql(
			"""
			select name from `tabFacility Booking`
			where court = %(court)s
				and booking_date = %(date)s
				and booking_status not in ('Cancelled', 'No-show')
				and (start_time < %(end_time)s and end_time > %(start_time)s)
			limit 1
			""",
			{"court": self.court, "date": self.date, "start_time": self.start_time, "end_time": self.end_time},
		)
		if booking_conflict:
			frappe.throw(_("This slot conflicts with an existing Facility Booking on this court."))

		maintenance_conflict = frappe.db.sql(
			"""
			select name from `tabMaintenance Schedule`
			where court = %(court)s
				and scheduled_date = %(date)s
				and status in ('Scheduled', 'In Progress')
				and (scheduled_start < %(end_time)s and scheduled_end > %(start_time)s)
			limit 1
			""",
			{"court": self.court, "date": self.date, "start_time": self.start_time, "end_time": self.end_time},
		)
		if maintenance_conflict:
			frappe.throw(_("This slot conflicts with a scheduled Maintenance window on this court."))

		training_conflict = frappe.db.sql(
			"""
			select name from `tabTraining Session`
			where court = %(court)s
				and date = %(date)s
				and docstatus != 2
				and (start_time < %(end_time)s and end_time > %(start_time)s)
			limit 1
			""",
			{"court": self.court, "date": self.date, "start_time": self.start_time, "end_time": self.end_time},
		)
		if training_conflict:
			frappe.throw(_("This slot conflicts with an existing Training Session on this court."))

		session_conflict = frappe.db.sql(
			"""
			select name from `tabPlayer Session`
			where court = %(court)s
				and date = %(date)s
				and docstatus != 2
				and name != %(name)s
				and (start_time < %(end_time)s and end_time > %(start_time)s)
			limit 1
			""",
			{
				"court": self.court,
				"date": self.date,
				"start_time": self.start_time,
				"end_time": self.end_time,
				"name": self.name or "",
			},
		)
		if session_conflict:
			frappe.throw(_("This slot conflicts with another Player Session on this court."))

	def set_total_amount(self):
		if self.rate and self.date and self.start_time and self.end_time:
			duration_hours = time_diff_in_hours(
				get_datetime(f"{self.date} {self.end_time}"), get_datetime(f"{self.date} {self.start_time}")
			)
			self.total_amount = flt(self.rate) * duration_hours

	def on_submit(self):
		self.create_session_invoice()

	def on_cancel(self):
		cancel_linked_invoice(self.sales_invoice)

	def create_session_invoice(self):
		"""One invoice per session, billed to whichever Customer the
		player_registration's Member resolves to - same pattern as Training
		Session.create_session_invoice(), just for a single fixed
		participant instead of a table of them."""
		if not self.total_amount or not self.player_registration:
			return

		member = frappe.db.get_value("Player Registration", self.player_registration, "member")
		customer = get_member_customer(member)
		if not customer:
			frappe.msgprint(
				_("No linked Customer found for this booking - skipping invoice creation."),
				alert=True,
			)
			return

		si = make_linked_sales_invoice(
			customer=customer,
			item_code="Player Session Fee",
			item_group="Coaching",
			amount=self.total_amount,
			link_fieldname="player_session",
			link_docname=self.name,
			description=f"Player Session {self.name} with {self.player}",
		)
		si.submit()
		self.db_set("sales_invoice", si.name)


# ---------------------------------------------------------------------
# "Book a Player" - public 1-on-1-with-a-roster-Player booking
#
# Distinct from "Book a Coach" (doctype/training_session/training_session.py,
# whose public functions this file's docstring used to live under before
# the two were split apart): that page books a Coach and creates a
# Training Session; this page books a specific roster Player and creates
# a Player Session. Both share the same guest-OTP identity flow
# (sports_complex/utils/guest_booking.py) and the same Member/Player
# Registration resolution helpers - imported from training_session.py
# rather than duplicated, since neither helper has anything coach- or
# player-specific in it.
#
# Availability works the same way as a Coach's: a Player Availability
# child table (mirroring Coach Availability) on the Player doctype
# defines their bookable weekly windows, minus whatever Player Sessions
# they already have that day. A court is picked the same way Training
# Session picks one - the first free active facility, since nothing in
# the schema ties a Player to a preferred court either.
# ---------------------------------------------------------------------


@frappe.whitelist(allow_guest=True)
def list_bookable_players():
	"""Guest-safe read data for a public Book a Player grid - Player name,
	photo, hourly rate, and today's open-slot count. Only Players who are
	both Active and have a rate configured are offered - an Active Player
	with no hourly_rate set has never been priced for private booking."""
	players = frappe.get_all(
		"Player",
		filters={"status": "Active", "hourly_rate": [">", 0]},
		fields=["name", "full_name", "hourly_rate", "profile_photo", "position"],
		order_by="full_name asc",
	)
	today = nowdate()
	for p in players:
		p["open_slots_today"] = len(get_player_available_slots(p["name"], today))
	return players


@frappe.whitelist(allow_guest=True)
def get_player_available_slots(player, date):
	"""Open time ranges to book this Player on a given date - the Player
	counterpart to Training Session's own get_coach_available_slots()."""
	from sports_complex.sports_complex.doctype.facility_booking.facility_booking import (
		_format_time,
		_padded,
		_split_into_slots,
		_subtract_busy,
	)

	day_of_week = get_datetime(date).strftime("%A")
	windows = frappe.get_all(
		"Player Availability",
		filters={"parent": player, "parenttype": "Player", "day_of_week": day_of_week},
		fields=["start_time", "end_time"],
		order_by="start_time asc",
	)
	if not windows:
		return []

	duration = cint(frappe.db.get_single_value("Sports Complex Setup", "default_booking_duration")) or 60
	buffer_minutes = flt(frappe.db.get_single_value("Sports Complex Setup", "buffer_time_between_bookings"))

	busy = []
	for row in frappe.get_all(
		"Player Session",
		filters={"player": player, "date": date, "docstatus": ("<", 2)},
		fields=["start_time", "end_time"],
	):
		busy.append(_padded(row.start_time, row.end_time, buffer_minutes))

	slots = []
	for window in windows:
		for free_start, free_end in _subtract_busy(window.start_time, window.end_time, busy):
			for slot_start, slot_end in _split_into_slots(free_start, free_end, duration):
				slots.append({"start_time": _format_time(slot_start), "end_time": _format_time(slot_end)})
	return slots


def _find_free_facility_for_slot(date, start_time, end_time):
	"""Same idea as Training Session's own _find_free_facility_for_slot() -
	reuses PlayerSession.validate_court_conflict() itself against an
	in-memory (never inserted) doc for each candidate facility, rather than
	duplicating its conflict SQL here."""
	temp = frappe.new_doc("Player Session")
	temp.date = date
	temp.start_time = start_time
	temp.end_time = end_time
	for facility in frappe.get_all("Sports Facility", filters={"status": "Active"}, pluck="name"):
		temp.court = facility
		try:
			temp.validate_court_conflict()
			return facility
		except frappe.ValidationError:
			continue
	return None


def _issue_payment_link_if_any(sales_invoice):
	"""Same generic frappe_paystack helper Training Session's own
	_issue_payment_link_if_any() delegates to."""
	if not sales_invoice:
		return None
	from frappe_paystack.api import create_payment_link

	try:
		return create_payment_link("Sales Invoice", sales_invoice)
	except Exception:
		frappe.log_error(title="Sports Complex: Book a Player - failed to create payment link")
		return None


def _book_player_session(player, date, start_time, end_time, player_registration, notes):
	court = _find_free_facility_for_slot(date, start_time, end_time)
	if not court:
		frappe.throw(_("No facility is free for this time slot - please pick another time."))

	player_doc = frappe.get_cached_doc("Player", player)

	session = frappe.new_doc("Player Session")
	session.player = player
	session.court = court
	session.date = date
	session.start_time = start_time
	session.end_time = end_time
	session.rate = flt(player_doc.hourly_rate)
	session.player_registration = player_registration
	session.flags.ignore_permissions = True
	session.insert()
	session.submit()
	if notes:
		# Player Session has no notes field of its own (same reasoning as
		# Training Session) - a comment is the closest real place to keep
		# whatever the customer typed rather than silently dropping it.
		session.add_comment("Comment", notes)

	return {
		"player_session": session.name,
		"payment_link": _issue_payment_link_if_any(session.sales_invoice),
	}


@frappe.whitelist()
def create_player_booking(
	player,
	date,
	start_time,
	end_time,
	full_name,
	date_of_birth,
	notes=None,
	guardian_name=None,
	guardian_relationship=None,
	guardian_contact=None,
	guardian_email=None,
	consent_given=0,
):
	"""Self-service entry point for a logged-in member/customer to book a
	session with a specific roster Player themselves - the "Book a Player"
	counterpart to Training Session's own create_training_booking()."""
	from sports_complex.sports_complex.doctype.facility_booking.facility_booking import (
		_resolve_member_contact,
		resolve_session_customer,
	)
	from sports_complex.sports_complex.doctype.training_session.training_session import (
		_resolve_member_for_customer,
		_resolve_or_create_player_registration,
	)

	customer = resolve_session_customer()
	if not customer:
		frappe.throw(
			_("No Customer record is linked to your account. Contact the front desk to book."),
			frappe.PermissionError,
		)

	email, phone = _resolve_member_contact(customer)
	member = _resolve_member_for_customer(customer, full_name=full_name, email=email, phone=phone)
	registration = _resolve_or_create_player_registration(
		member, full_name, date_of_birth, guardian_name, guardian_relationship,
		guardian_contact, guardian_email, consent_given,
	)

	return _book_player_session(player, date, start_time, end_time, registration.name, notes)


@frappe.whitelist(allow_guest=True, methods=["POST"])
def create_guest_player_booking(
	player,
	date,
	start_time,
	end_time,
	email,
	full_name,
	date_of_birth,
	otp=None,
	remember_token=None,
	phone=None,
	notes=None,
	guardian_name=None,
	guardian_relationship=None,
	guardian_contact=None,
	guardian_email=None,
	consent_given=0,
):
	"""Guest counterpart to create_player_booking() - same emailed-OTP
	identity flow Facility Booking/Training Session's own guest booking
	functions use (sports_complex.utils.guest_booking), reused as-is."""
	from sports_complex.sports_complex.doctype.training_session.training_session import (
		_resolve_member_for_customer,
		_resolve_or_create_player_registration,
	)
	from sports_complex.utils.guest_booking import (
		issue_booking_remember_token,
		resolve_or_create_guest_customer,
		verify_booking_otp,
		verify_booking_remember_token,
	)

	normalized_email = (email or "").strip().lower()
	if not (remember_token and verify_booking_remember_token(normalized_email, remember_token)):
		verify_booking_otp(email, otp)

	customer = resolve_or_create_guest_customer(email, full_name, phone)
	member = _resolve_member_for_customer(customer, full_name=full_name, email=email, phone=phone)
	registration = _resolve_or_create_player_registration(
		member, full_name, date_of_birth, guardian_name, guardian_relationship,
		guardian_contact, guardian_email, consent_given,
	)

	result = _book_player_session(player, date, start_time, end_time, registration.name, notes)
	result["remember_token"] = issue_booking_remember_token(normalized_email)
	return result
