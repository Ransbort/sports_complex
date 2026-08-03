# Copyright (c) 2026, Sports Complex and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class Results(Document):
	def validate(self):
		self.enforce_one_result_per_match()
		if not (self.winner_team or self.winner_player):
			frappe.msgprint(_("No winner set yet."), alert=True)

	def enforce_one_result_per_match(self):
		existing = frappe.db.get_value(
			"Results", {"match": self.match, "name": ["!=", self.name or ""]}, "name"
		)
		if existing:
			frappe.throw(_("Match {0} already has a Result recorded: {1}").format(self.match, existing))

	def on_update(self):
		# Mark the Match completed once a result is captured
		if self.match:
			frappe.db.set_value("Match", self.match, "status", "Completed")
