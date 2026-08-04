# Copyright (c) 2026, Sports Complex and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from sports_complex.utils import get_member_customer, make_linked_sales_invoice


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

	def create_entry_fee_invoice(self):
		if not self.fee:
			return

		customer = None
		if self.player:
			member = frappe.db.get_value("Player Registration", self.player, "member")
			customer = get_member_customer(member)
		elif self.team and self.team_roster_has_members():
			# bill the first roster member's linked customer
			roster = frappe.get_all(
				"Team Member", filters={"parent": self.team}, fields=["player"], limit_page_length=1
			)
			if roster:
				member = frappe.db.get_value("Player Registration", roster[0].player, "member")
				customer = get_member_customer(member)

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
		self.db_set("sales_invoice", si.name)
		if self.status == "Pending":
			self.db_set("status", "Confirmed")

	def team_roster_has_members(self):
		return bool(frappe.db.count("Team Member", {"parent": self.team}))
