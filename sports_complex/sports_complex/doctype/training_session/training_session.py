# Copyright (c) 2026, Sports Complex and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, get_datetime, nowdate, time_diff_in_hours

from sports_complex.utils import cancel_linked_invoice, get_member_customer, make_linked_sales_invoice


class TrainingSession(Document):
	def validate(self):
		self.validate_court_conflict()

	def validate_court_conflict(self):
		"""A Training Session consumes a Court slot - make sure it doesn't
		overlap an existing Facility Booking or Maintenance Schedule on the
		same court/date, and not another Training Session either."""
		if not (self.court and self.date and self.start_time and self.end_time):
			return

		overlap_filters_common = {
			"court": self.court,
			"name": ["!=", self.name],
		}

		# Facility Booking overlap
		booking_conflict = frappe.db.sql(
			"""
			select name from `tabFacility Booking`
			where court = %(court)s
				and booking_date = %(date)s
				and booking_status not in ('Cancelled', 'No-show')
				and (start_time < %(end_time)s and end_time > %(start_time)s)
			limit 1
			""",
			{
				"court": self.court,
				"date": self.date,
				"start_time": self.start_time,
				"end_time": self.end_time,
			},
		)
		if booking_conflict:
			frappe.throw(_("This slot conflicts with an existing Facility Booking on this court."))

		# Maintenance Schedule overlap
		maintenance_conflict = frappe.db.sql(
			"""
			select name from `tabMaintenance Schedule`
			where court = %(court)s
				and scheduled_date = %(date)s
				and status in ('Scheduled', 'In Progress')
				and (scheduled_start < %(end_time)s and scheduled_end > %(start_time)s)
			limit 1
			""",
			{
				"court": self.court,
				"date": self.date,
				"start_time": self.start_time,
				"end_time": self.end_time,
			},
		)
		if maintenance_conflict:
			frappe.throw(_("This slot conflicts with a scheduled Maintenance window on this court."))

		# Other Training Sessions
		session_conflict = frappe.db.sql(
			"""
			select name from `tabTraining Session`
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
			frappe.throw(_("This slot conflicts with another Training Session on this court."))

		if len(self.participants or []) > 0 and self.max_participants_limit():
			pass

	def max_participants_limit(self):
		if self.training_schedule:
			max_p = frappe.db.get_value("Training Schedule", self.training_schedule, "max_participants")
			if max_p and len(self.participants or []) > max_p:
				frappe.throw(_("Number of participants exceeds the Training Schedule's max of {0}.").format(max_p))
		return True

	def on_submit(self):
		self.create_session_invoice()

	def on_cancel(self):
		cancel_linked_invoice(self.sales_invoice)

	def create_session_invoice(self):
		"""One invoice per session, billed to the first participant's linked
		Member/Customer for the total of fee_per_participant * headcount.
		If you'd rather bill each participant separately, loop and call
		make_linked_sales_invoice per participant instead."""
		if not self.fee_per_participant or not self.participants:
			return

		# Try to find a billable customer: prefer the first participant's Member
		customer = None
		for row in self.participants:
			member = frappe.db.get_value("Player Registration", row.player, "member")
			customer = get_member_customer(member)
			if customer:
				break

		if not customer:
			frappe.msgprint(
				_("No linked Customer found for participants - skipping invoice creation."),
				alert=True,
			)
			return

		total = self.fee_per_participant * len(self.participants)
		si = make_linked_sales_invoice(
			customer=customer,
			item_code="Training Session Fee",
			item_group="Coaching",
			amount=total,
			link_fieldname="training_session",
			link_docname=self.name,
			description=f"Training Session {self.name} ({len(self.participants)} participant(s))",
		)
		si.submit()
		self.db_set("sales_invoice", si.name)


# ---------------------------------------------------------------------
# "Book a Coach" - public coaching-session booking
#
# Coach's own desk-only permissions don't extend to Guest/Customer, so a
# public page can't call frappe.client methods against it directly -
# same reason Facility Booking has its own public front door (list_
# bookable_facilities/get_available_slots/create_booking/create_guest_
# booking in facility_booking.py). Everything below mirrors that shape.
#
# A Training Session requires a court (Sports Facility) just like a
# direct Facility Booking does, but this flow never asks the customer to
# pick one - _find_free_facility_for_slot() below picks the first active
# facility with no conflict, since nothing in the schema links a Coach
# to a preferred/compatible Facility Type to filter by. Worth revisiting
# if a coach ends up needing one specific court in practice.
#
# "Book a Coach" also skips two things Facility Booking's own guest
# flow has: a confirmation email, and a signed per-booking access token
# for a guest to look up/cancel a session later (My Bookings has no
# Training Session equivalent yet). The returned payment_link covers
# the one thing that can't wait - collecting payment - immediately.
# ---------------------------------------------------------------------


@frappe.whitelist(allow_guest=True)
def list_bookable_coaches():
	"""Guest-safe read data for a public Book a Coach grid - Coach name,
	specialization (sport) tags, hourly rate, and today's open-slot count,
	the same shape list_bookable_facilities() returns for facilities."""
	coaches = frappe.get_all(
		"Coach",
		filters={"is_active": 1},
		fields=["name", "coach_name", "hourly_rate", "photo"],
		order_by="coach_name asc",
	)
	today = nowdate()
	for c in coaches:
		c["specializations"] = frappe.get_all(
			"Coach Specialization", filters={"parent": c["name"]}, pluck="sport", order_by="idx asc"
		)
		c["open_slots_today"] = len(get_coach_available_slots(c["name"], today))
	return coaches


@frappe.whitelist(allow_guest=True)
def get_coach_available_slots(coach, date):
	"""Open time ranges to book this coach on a given date: each of their
	weekly Coach Availability windows for that day of week, minus
	whatever Training Sessions they already have that day - the coach-
	side counterpart to Facility Booking's own get_available_slots().
	Slot length comes from Sports Complex Setup's Default Booking
	Duration (the same site-wide default Facility Booking falls back to
	via Booking Schedule) since neither Coach nor Training Session has a
	duration setting of its own.
	"""
	from sports_complex.sports_complex.doctype.facility_booking.facility_booking import (
		_format_time,
		_padded,
		_split_into_slots,
		_subtract_busy,
	)

	day_of_week = get_datetime(date).strftime("%A")
	windows = frappe.get_all(
		"Coach Availability",
		filters={"parent": coach, "parenttype": "Coach", "day_of_week": day_of_week},
		fields=["start_time", "end_time"],
		order_by="start_time asc",
	)
	if not windows:
		return []

	duration = cint(frappe.db.get_single_value("Sports Complex Setup", "default_booking_duration")) or 60
	buffer_minutes = flt(frappe.db.get_single_value("Sports Complex Setup", "buffer_time_between_bookings"))

	busy = []
	for row in frappe.get_all(
		"Training Session",
		filters={"coach": coach, "date": date, "docstatus": ("<", 2)},
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
	"""Pick the first active Sports Facility with no Facility Booking/
	Maintenance Schedule/other Training Session conflict at this date+
	time, by reusing TrainingSession.validate_court_conflict() itself
	against an in-memory (never inserted) doc for each candidate in turn,
	rather than duplicating its conflict SQL here. Read-only - validate_
	court_conflict() only queries the DB, so this is safe to call on a
	doc that's never saved.
	"""
	temp = frappe.new_doc("Training Session")
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


def _resolve_member_for_customer(customer, full_name=None, email=None, phone=None):
	"""Member and Customer are meant to be 1:1 (Member.before_insert auto-
	creates its own Customer), but a Customer reached here could in
	principle predate that link (e.g. one created outside this app's own
	flows). Create the missing Member record pointed at the *existing*
	Customer in that case, rather than letting Member.before_insert spin
	up a second, disconnected one.
	"""
	member = frappe.db.get_value("Member", {"customer": customer}, "name")
	if member:
		return member

	member_doc = frappe.new_doc("Member")
	member_doc.member_name = full_name or customer
	member_doc.customer = customer
	if email:
		member_doc.email = email
	if phone:
		member_doc.phone = phone
	member_doc.flags.ignore_permissions = True
	member_doc.insert()
	return member_doc.name


def _resolve_or_create_player_registration(
	member,
	player_name,
	date_of_birth,
	guardian_name=None,
	guardian_relationship=None,
	guardian_contact=None,
	guardian_email=None,
	consent_given=0,
):
	"""Find-or-create the Player Registration a Training Session
	Participant row needs (create_session_invoice() bills whichever
	Customer that record's own `member` resolves to - no Player
	Registration means no invoice). One Member is assumed to have at
	most one Player Registration - reuse and refresh it with whatever
	was typed for *this* booking rather than creating a duplicate every
	time the same person books again, same rationale as guest_booking.
	resolve_or_create_guest_customer().
	"""
	existing = frappe.db.get_value("Player Registration", {"member": member}, "name")
	doc = frappe.get_doc("Player Registration", existing) if existing else frappe.new_doc("Player Registration")
	doc.member = member
	doc.player_name = player_name
	doc.date_of_birth = date_of_birth
	if guardian_name:
		doc.guardian_name = guardian_name
	if guardian_relationship:
		doc.guardian_relationship = guardian_relationship
	if guardian_contact:
		doc.guardian_contact = guardian_contact
	if guardian_email:
		doc.guardian_email = guardian_email
	if cint(consent_given):
		doc.consent_given = 1
		doc.consent_date = nowdate()

	doc.flags.ignore_permissions = True
	try:
		doc.save()
	except frappe.DuplicateEntryError:
		# player_name is this doctype's own naming field (autoname:
		# field:player_name) - a different Member who happens to share an
		# identical full name would otherwise collide on insert.
		# Disambiguate with the Member id rather than failing the whole
		# booking over a naming clash that has nothing to do with the
		# person actually booking.
		doc.player_name = f"{player_name} ({member})"
		doc.save()
	return doc


def _issue_payment_link_if_any(sales_invoice):
	"""Same generic frappe_paystack helper Facility Booking's own
	get_booking_payment_link() delegates to - a Training Session/
	Tournament Registration's linked invoice is always already submitted
	by the time this runs (create_session_invoice()/create_entry_fee_
	invoice() submit it themselves on_submit), so there's no "not
	submitted yet" guard to duplicate here.
	"""
	if not sales_invoice:
		return None
	from frappe_paystack.api import create_payment_link

	try:
		return create_payment_link("Sales Invoice", sales_invoice)
	except Exception:
		frappe.log_error(title="Sports Complex: Book a Coach - failed to create payment link")
		return None


def _book_training_session(coach, date, start_time, end_time, player_registration, notes):
	court = _find_free_facility_for_slot(date, start_time, end_time)
	if not court:
		frappe.throw(_("No facility is free for this time slot - please pick another time."))

	coach_doc = frappe.get_cached_doc("Coach", coach)
	# get_datetime() first, same as Facility Booking's own calculate_
	# duration_and_amount() - time_diff_in_hours() is happy to accept raw
	# strings too, but matching the established convention exactly here
	# avoids relying on that leniency.
	duration_hours = time_diff_in_hours(
		get_datetime(f"{date} {end_time}"), get_datetime(f"{date} {start_time}")
	)

	session = frappe.new_doc("Training Session")
	session.coach = coach
	session.court = court
	session.date = date
	session.start_time = start_time
	session.end_time = end_time
	session.fee_per_participant = flt(coach_doc.hourly_rate) * duration_hours
	session.append("participants", {"player": player_registration})
	session.flags.ignore_permissions = True
	session.insert()
	session.submit()
	if notes:
		# Training Session has no notes field of its own (unlike Facility
		# Booking) - a comment is the closest real place to keep whatever
		# the customer typed rather than silently dropping it.
		session.add_comment("Comment", notes)

	return {
		"training_session": session.name,
		"payment_link": _issue_payment_link_if_any(session.sales_invoice),
	}


@frappe.whitelist()
def create_training_booking(
	coach,
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
	coaching session themselves - the "Book a Coach" counterpart to
	Facility Booking's own create_booking(). full_name/date_of_birth
	(plus guardian_* when the computed age comes out under 18 - see
	Player Registration.validate_guardian_consent()) describe who's
	actually training, which is usually the logged-in customer but need
	not be (a parent booking for their child, say).
	"""
	from sports_complex.sports_complex.doctype.facility_booking.facility_booking import (
		_resolve_member_contact,
		resolve_session_customer,
	)

	customer = resolve_session_customer()
	if not customer:
		frappe.throw(
			_("No Customer record is linked to your account. Contact the front desk to book."),
			frappe.PermissionError,
		)

	email, phone = _resolve_member_contact(customer)
	member = _resolve_member_for_customer(customer, full_name=full_name, email=email, phone=phone)
	player = _resolve_or_create_player_registration(
		member, full_name, date_of_birth, guardian_name, guardian_relationship,
		guardian_contact, guardian_email, consent_given,
	)

	return _book_training_session(coach, date, start_time, end_time, player.name, notes)


@frappe.whitelist(allow_guest=True, methods=["POST"])
def create_guest_training_booking(
	coach,
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
	"""Guest counterpart to create_training_booking() - same emailed-OTP
	identity flow Facility Booking's own create_guest_booking() uses
	(sports_complex.utils.guest_booking), reused as-is rather than
	duplicated. remember_token, when it verifies, stands in for otp
	entirely - see guest_booking.verify_booking_remember_token's own
	docstring.
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

	customer = resolve_or_create_guest_customer(email, full_name, phone)
	member = _resolve_member_for_customer(customer, full_name=full_name, email=email, phone=phone)
	player = _resolve_or_create_player_registration(
		member, full_name, date_of_birth, guardian_name, guardian_relationship,
		guardian_contact, guardian_email, consent_given,
	)

	result = _book_training_session(coach, date, start_time, end_time, player.name, notes)
	result["remember_token"] = issue_booking_remember_token(normalized_email)
	return result
