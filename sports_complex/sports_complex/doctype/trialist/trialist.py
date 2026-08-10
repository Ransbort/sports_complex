# Copyright (c) 2026, Pep Sports Limited and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import today


class Trialist(Document):
	def validate(self):
		self.set_full_name()

	def set_full_name(self):
		self.full_name = " ".join(
			part for part in [self.first_name, self.last_name] if part
		).strip()


def _guard_not_already_converted(trialist_doc):
	if trialist_doc.player:
		frappe.throw(
			_("Trialist {0} has already been converted to Player {1}.").format(
				trialist_doc.name, trialist_doc.player
			)
		)


@frappe.whitelist()
def convert_trialist_to_player(trialist, team=None, jersey_number=None, player_category=None, joining_date=None):
	"""Trialist → Player conversion ("Mark as Player" / "Register as
	Player"). Called from trialist.js's custom button after the
	operator fills in the small supplementary form (team, jersey
	number, player category, joining date) — those are the only
	fields that don't already exist on the Trialist's own registration
	data, per the meeting notes: "a small additional form supplements
	their already-filled registration data".

	Everything else on the new Player record is copied straight across
	from the Trialist rather than re-entered, since it was already
	captured on the original hard-copy registration form.
	"""

	trialist_doc = frappe.get_doc("Trialist", trialist)
	_guard_not_already_converted(trialist_doc)

	player_doc = frappe.get_doc({
		"doctype": "Player",
		"trialist": trialist_doc.name,

		"first_name": trialist_doc.first_name,
		"last_name": trialist_doc.last_name,
		"image": trialist_doc.image,
		"gender": trialist_doc.gender,
		"date_of_birth": trialist_doc.date_of_birth,
		"mobile_number": trialist_doc.mobile_number,
		"guardian_name": trialist_doc.guardian_name,
		"guardian_contact": trialist_doc.guardian_contact,
		"address": trialist_doc.address,
		"emergency_contact_name": trialist_doc.emergency_contact_name,
		"emergency_contact_number": trialist_doc.emergency_contact_number,
		"position": trialist_doc.position,

		# Supplied by the small supplementary form at conversion time —
		# team defaults to whatever the trialist was already grouped
		# into during trials, but the operator can override it (final
		# squad placement doesn't always match the trial group).
		"team": team or trialist_doc.preferred_team,
		"jersey_number": jersey_number,
		"player_category": player_category,
		"joining_date": joining_date or today(),
	})

	player_doc.insert(ignore_permissions=True)

	trialist_doc.db_set("player", player_doc.name)
	trialist_doc.db_set("status", "Converted to Player")
	trialist_doc.db_set("converted_on", today())

	return {
		"status": "Success",
		"player": player_doc.name,
	}
