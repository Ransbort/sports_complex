# Copyright (c) 2026, Sports Complex and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class Fixtures(Document):
	def validate(self):
		has_teams = bool(self.team_a or self.team_b)
		has_players = bool(self.player_a or self.player_b)
		if has_teams and has_players:
			frappe.throw(_("Use either Team A/B or Player A/B for a fixture, not both."))

	@frappe.whitelist()
	def create_match(self):
		"""Promote this fixture to a played Match. Called from a form button
		once the fixture's scheduled slot is confirmed."""
		if self.match:
			frappe.throw(_("A Match already exists for this fixture: {0}").format(self.match))

		match = frappe.new_doc("Match")
		match.fixture = self.name
		match.court = self.court
		if self.scheduled_date and self.scheduled_time:
			match.actual_date_time = f"{self.scheduled_date} {self.scheduled_time}"
		match.insert(ignore_permissions=True)

		self.db_set("match", match.name)
		return match.name
