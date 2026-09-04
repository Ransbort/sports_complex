# Copyright (c) 2026, Sports Complex and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from sports_complex.utils import cancel_linked_invoice, get_member_customer, make_linked_sales_invoice


class TournamentRegistration(Document):
	def validate(self):
		if not (self.team or self.player):
			frappe.throw(_("Register either a Team or a Player."))
		if self.tournament:
			self.fee = frappe.db.get_value("Tournament", self.tournament, "entry_fee") or 0
		self.enforce_capacity()

	def enforce_capacity(self):
		tournament = frappe.get_cached_doc("Tournament", self.tournament)
		confirmed = frappe.db.count(
			"Tournament Registration",
			{
				"tournament": self.tournament,
				"status": "Confirmed",
				"name": ["!=", self.name or ""],
			},
		)
		limit = tournament.max_teams if tournament.registration_type == "Team" else tournament.max_players
		if limit and confirmed >= limit and self.status == "Confirmed":
			self.status = "Waitlisted"
			frappe.msgprint(_("Tournament is at capacity - registration set to Waitlisted."), alert=True)

	def on_submit(self):
		self.create_entry_fee_invoice()

	def on_cancel(self):
		self.db_set("status", "Cancelled")
		cancel_linked_invoice(self.sales_invoice)

	def create_entry_fee_invoice(self):
		if not self.fee:
			return

		customer = None
		if self.player:
			member = frappe.db.get_value("Player Registration", self.player, "member")
			customer = get_member_customer(member)
		elif self.team and self.team_roster_has_members():
			# bill the first roster member's linked customer. Team Member's
			# own `player` field links to Player (the internal squad
			# profile, jersey number/position/etc - see doctype/player/
			# player.json), not Player Registration (the public self-
			# service signup doctype Tournament Registration's own
			# `player` field above links to) - those are two different
			# doctypes with two different naming schemes. This used to
			# look `roster[0].player` up as if it were a Player
			# Registration name instead, which meant it almost never
			# resolved to a real record and this branch silently fell
			# through to "No linked Customer found" for every Team
			# registration. Player already carries its own billing
			# Customer directly (see Player's "Billing" section), so
			# there's no need to go through Member/get_member_customer at
			# all here.
			roster = frappe.get_all(
				"Team Member", filters={"parent": self.team}, fields=["player"], limit_page_length=1
			)
			if roster:
				customer = frappe.db.get_value("Player", roster[0].player, "customer")

		if not customer:
			frappe.msgprint(
				_("No linked Customer found - please set one manually and re-create the invoice."),
				alert=True,
			)
			return

		si = make_linked_sales_invoice(
			customer=customer,
			item_code="Tournament Entry Fee",
			item_group="Tournament",
			amount=self.fee,
			link_fieldname="tournament_registration",
			link_docname=self.name,
			description=f"Entry fee - {self.tournament}",
		)
		si.submit()
		self.db_set("sales_invoice", si.name)
		if self.status == "Pending":
			self.db_set("status", "Confirmed")

	def team_roster_has_members(self):
		return bool(frappe.db.count("Team Member", {"parent": self.team}))


# ---------------------------------------------------------------------
# "Register for a Tournament" - public tournament entry
#
# Same reasoning as Training Session's own "Book a Player" front door
# (see the bottom of training_session.py): Tournament/Tournament
# Registration's desk-only permissions don't extend to Guest/Customer,
# so a public page needs its own read-only listing and its own guarded
# create entry points, mirroring Facility Booking's shape once again.
#
# Team registrations pick from the club's existing Teams rather than
# creating one on the fly - a Team carries a coach and a curated roster
# (see team.json), not something this public flow is meant to spin up.
# Player registrations reuse the exact same Player Registration find-
# or-create helper Book a Player uses, imported from training_session.py
# rather than duplicated.
# ---------------------------------------------------------------------


@frappe.whitelist(allow_guest=True)
def list_open_tournaments():
	"""Guest-safe read data for a public Register for a Tournament grid -
	only "Upcoming" tournaments (Ongoing/Completed/Cancelled ones aren't
	open for new entries), with each one's remaining capacity so a
	tournament sitting at max_teams/max_players can show as full instead
	of quietly waitlisting whoever tries anyway.
	"""
	tournaments = frappe.get_all(
		"Tournament",
		filters={"status": "Upcoming"},
		fields=[
			"name", "tournament_name", "sport", "venue", "start_date", "end_date",
			"entry_fee", "registration_type", "max_teams", "max_players", "photo",
		],
		order_by="start_date asc",
	)
	for t in tournaments:
		limit = t.max_teams if t.registration_type == "Team" else t.max_players
		confirmed = frappe.db.count(
			"Tournament Registration", {"tournament": t.name, "status": "Confirmed"}
		)
		t["spots_remaining"] = max(limit - confirmed, 0) if limit else None
	return tournaments


@frappe.whitelist(allow_guest=True)
def get_tournament_teams(tournament):
	"""Active Teams for a Team-type tournament's registration dropdown -
	filtered to the tournament's own sport, since a football Team has no
	business entering a basketball tournament."""
	sport = frappe.db.get_value("Tournament", tournament, "sport")
	filters = {"is_active": 1}
	if sport:
		filters["sport"] = sport
	return frappe.get_all("Team", filters=filters, fields=["name", "team_name", "age_group", "division"], order_by="team_name asc")


def _create_and_submit_registration(tournament, team=None, player_registration=None):
	registration = frappe.new_doc("Tournament Registration")
	registration.tournament = tournament
	if team:
		registration.team = team
	if player_registration:
		registration.player = player_registration
	registration.flags.ignore_permissions = True
	registration.insert()
	registration.submit()

	from sports_complex.sports_complex.doctype.training_session.training_session import (
		_issue_payment_link_if_any,
	)

	return {
		"tournament_registration": registration.name,
		"status": registration.status,
		"payment_link": _issue_payment_link_if_any(registration.sales_invoice),
	}


@frappe.whitelist()
def create_tournament_registration(
	tournament,
	team=None,
	full_name=None,
	date_of_birth=None,
	guardian_name=None,
	guardian_relationship=None,
	guardian_contact=None,
	guardian_email=None,
	consent_given=0,
):
	"""Self-service entry point for a logged-in member/customer to enter a
	tournament themselves - branches on the tournament's own
	registration_type exactly like the doctype's own validate() expects
	(team XOR player). Player-path args mirror create_training_booking()
	and go through the same Player Registration find-or-create helper.
	"""
	from sports_complex.sports_complex.doctype.facility_booking.facility_booking import (
		_resolve_member_contact,
		resolve_session_customer,
	)
	from sports_complex.sports_complex.doctype.training_session.training_session import (
		_resolve_member_for_customer,
		_resolve_or_create_player_registration,
	)

	registration_type = frappe.db.get_value("Tournament", tournament, "registration_type")

	if registration_type == "Team":
		if not team:
			frappe.throw(_("Select a Team to register."))
		return _create_and_submit_registration(tournament, team=team)

	customer = resolve_session_customer()
	if not customer:
		frappe.throw(
			_("No Customer record is linked to your account. Contact the front desk to register."),
			frappe.PermissionError,
		)
	if not (full_name and date_of_birth):
		frappe.throw(_("Player name and date of birth are required."))

	email, phone = _resolve_member_contact(customer)
	member = _resolve_member_for_customer(customer, full_name=full_name, email=email, phone=phone)
	player = _resolve_or_create_player_registration(
		member, full_name, date_of_birth, guardian_name, guardian_relationship,
		guardian_contact, guardian_email, consent_given,
	)
	return _create_and_submit_registration(tournament, player_registration=player.name)


@frappe.whitelist(allow_guest=True, methods=["POST"])
def create_guest_tournament_registration(
	tournament,
	email,
	full_name,
	date_of_birth=None,
	team=None,
	otp=None,
	remember_token=None,
	phone=None,
	guardian_name=None,
	guardian_relationship=None,
	guardian_contact=None,
	guardian_email=None,
	consent_given=0,
):
	"""Guest counterpart to create_tournament_registration() - same
	emailed-OTP identity flow every other guest flow in this app uses
	(sports_complex.utils.guest_booking), reused as-is. Still asks for an
	email/OTP on the Team path (to know who to email about the
	registration) even though Team billing resolves through the roster's
	own linked Customer rather than this guest's - see
	create_entry_fee_invoice()'s own comment on that.
	"""
	from sports_complex.utils.guest_booking import (
		issue_booking_remember_token,
		resolve_or_create_guest_customer,
		verify_booking_otp,
		verify_booking_remember_token,
	)
	from sports_complex.sports_complex.doctype.training_session.training_session import (
		_resolve_member_for_customer,
		_resolve_or_create_player_registration,
	)

	normalized_email = (email or "").strip().lower()
	if not (remember_token and verify_booking_remember_token(normalized_email, remember_token)):
		verify_booking_otp(email, otp)

	registration_type = frappe.db.get_value("Tournament", tournament, "registration_type")

	if registration_type == "Team":
		if not team:
			frappe.throw(_("Select a Team to register."))
		result = _create_and_submit_registration(tournament, team=team)
	else:
		if not date_of_birth:
			frappe.throw(_("Player date of birth is required."))
		customer = resolve_or_create_guest_customer(email, full_name, phone)
		member = _resolve_member_for_customer(customer, full_name=full_name, email=email, phone=phone)
		player = _resolve_or_create_player_registration(
			member, full_name, date_of_birth, guardian_name, guardian_relationship,
			guardian_contact, guardian_email, consent_given,
		)
		result = _create_and_submit_registration(tournament, player_registration=player.name)

	result["remember_token"] = issue_booking_remember_token(normalized_email)
	return result
