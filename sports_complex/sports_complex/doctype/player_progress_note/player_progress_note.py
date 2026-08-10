# Copyright (c) 2026, Pep Sports Limited and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import today


class PlayerProgressNote(Document):
	def validate(self):
		if self.status == "Resolved" and not self.resolved_on:
			self.resolved_on = today()
		if self.status != "Resolved":
			# Don't leave a stale resolution date lying around if a note
			# gets reopened after being marked Resolved.
			self.resolved_on = None

	def on_update(self):
		_sync_open_issues_count(self.player)

	def on_trash(self):
		_sync_open_issues_count(self.player)


def _sync_open_issues_count(player):
	if not player:
		return

	open_count = frappe.db.count(
		"Player Progress Note",
		{"player": player, "status": ["!=", "Resolved"]},
	)
	frappe.db.set_value("Player", player, "open_issues_count", open_count, update_modified=False)
