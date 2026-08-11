# Copyright (c) 2026, Pep Sports Limited and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, today


class Trialist(Document):
	def validate(self):
		self.set_full_name()
		self.set_age()

	def set_full_name(self):
		self.full_name = " ".join(
			part for part in [self.first_name, self.middle_name, self.last_name] if part
		).strip()

	def set_age(self):
		self.age = _format_age(self.date_of_birth)


def _format_age(dob):
	"""Matches the "X years, Y days old" display seen in the original
	Trial_Athlete export. Approximate (365-day years, no leap-year
	correction) — good enough for a display-only field; don't rely on
	this for anything eligibility-critical, use date_of_birth directly
	for that instead."""

	if not dob:
		return None

	delta_days = (getdate(today()) - getdate(dob)).days
	years, days = divmod(delta_days, 365)

	year_label = _("year") if years == 1 else _("years")
	day_label = _("day") if days == 1 else _("days")

	return _("{0} {1}, {2} {3} old").format(years, year_label, days, day_label)


def _guard_not_already_converted(trialist_doc):
	if trialist_doc.player:
		frappe.throw(
			_("Trialist {0} has already been converted to Player {1}.").format(
				trialist_doc.name, trialist_doc.player
			)
		)


def _guard_medically_cleared(trialist_doc):
	"""Final sport-side data entry (and conversion to Player) can't happen
	until a doctor has cleared this trialist — see send_to_clinic() below
	and healthcare_integration.on_patient_encounter_submit(), which is
	what actually flips medical_clearance_status to "Cleared" once the
	linked Patient Encounter is submitted with fitness_result="Fit"."""
	if trialist_doc.medical_clearance_status != "Cleared":
		frappe.throw(
			_(
				"Trialist {0} has not been medically cleared yet (status: {1}). "
				"Send them to the clinic and wait for the doctor's clearance "
				"before registering them as a Player."
			).format(trialist_doc.name, trialist_doc.medical_clearance_status or _("Not Sent"))
		)


@frappe.whitelist()
def send_to_clinic(trialist):
	"""Front desk/sports-complex operator sends a registered trialist to
	the clinic for their medical exam. Creates (or reuses) a linked
	Patient in the Healthcare app and hands back its name so the
	front-end can open a fresh Patient Encounter for the doctor to fill
	in and submit — deliberately NOT inserting the Encounter here, since
	Patient Encounter has mandatory fields (e.g. appointment_type) that
	only the doctor filling in the form can sensibly supply.

	Safe to call again for a trialist whose previous encounter came back
	"Not Cleared" (e.g. re-trialing after injury recovery) - only blocks
	re-sending someone who is already Cleared or already mid-review with
	an outstanding encounter.
	"""

	trialist_doc = frappe.get_doc("Trialist", trialist)
	_guard_not_already_converted(trialist_doc)

	if trialist_doc.medical_clearance_status == "Cleared":
		frappe.throw(_("Trialist {0} is already medically cleared.").format(trialist_doc.name))
	if trialist_doc.medical_clearance_status == "Pending":
		frappe.throw(
			_(
				"Trialist {0} already has a medical encounter ({1}) awaiting the "
				"doctor's result."
			).format(trialist_doc.name, trialist_doc.medical_encounter)
		)

	if not trialist_doc.patient:
		patient = frappe.get_doc({
			"doctype": "Patient",
			"first_name": trialist_doc.first_name,
			"last_name": trialist_doc.last_name,
			"sex": trialist_doc.gender,
			"dob": trialist_doc.date_of_birth,
			"mobile": trialist_doc.mobile_number,
		})
		patient.insert(ignore_permissions=True)
		trialist_doc.db_set("patient", patient.name)
	else:
		patient = frappe.get_doc("Patient", trialist_doc.patient)

	trialist_doc.db_set("medical_clearance_status", "Pending")
	trialist_doc.db_set("medical_encounter", None)

	return {
		"status": "Success",
		"patient": patient.name,
		"patient_name": patient.patient_name,
	}


def _copy_child_table(source_rows, target_doc, target_fieldname):
	for row in source_rows or []:
		target_doc.append(target_fieldname, row.as_dict())


@frappe.whitelist()
def convert_trialist_to_player(trialist, team=None, jersey_number=None, player_category=None, joining_date=None):
	"""Trialist → Player conversion ("Mark as Player" / "Register as
	Player"). Called from trialist.js's custom button after the
	operator fills in the small supplementary form (team, jersey
	number, player category, joining date) — those are the only
	fields that don't already exist on the Trialist's own registration
	data, per the meeting notes: "a small additional form supplements
	their already-filled registration data".

	Everything else — including the medical info, identification,
	positions, and emergency contacts captured at trial registration —
	is copied straight across so it doesn't need re-entering.
	"""

	trialist_doc = frappe.get_doc("Trialist", trialist)
	_guard_not_already_converted(trialist_doc)
	_guard_medically_cleared(trialist_doc)

	player_doc = frappe.get_doc({
		"doctype": "Player",
		"trialist": trialist_doc.name,

		"first_name": trialist_doc.first_name,
		"middle_name": trialist_doc.middle_name,
		"last_name": trialist_doc.last_name,
		"profile_photo": trialist_doc.profile_photo,

		"gender": trialist_doc.gender,
		"date_of_birth": trialist_doc.date_of_birth,
		"nationality": trialist_doc.nationality,
		"mobile_number": trialist_doc.mobile_number,
		"email": trialist_doc.email,
		"address": trialist_doc.address,

		"identification_type": trialist_doc.identification_type,
		"identification_number": trialist_doc.identification_number,
		"identification_document": trialist_doc.identification_document,

		"dominant_foot": trialist_doc.dominant_foot,
		"position": trialist_doc.preferred_position,
		"secondary_position": trialist_doc.secondary_position,
		"current_playing_level": trialist_doc.current_playing_level,
		"previous_clubs": trialist_doc.previous_clubs,

		"known_allergies": trialist_doc.known_allergies,
		"chronic_medical_conditions": trialist_doc.chronic_medical_conditions,
		"previous_surgeries": trialist_doc.previous_surgeries,
		"current_medications": trialist_doc.current_medications,
		"previous_serious_injuries": trialist_doc.previous_serious_injuries,

		"customer": trialist_doc.customer,

		# Supplied by the small supplementary form at conversion time —
		# team defaults to whatever the trialist was already grouped
		# into during trials, but the operator can override it (final
		# squad placement doesn't always match the trial group).
		"team": team or trialist_doc.preferred_team,
		"jersey_number": jersey_number,
		"player_category": player_category,
		"joining_date": joining_date or today(),
	})

	_copy_child_table(trialist_doc.other_positions, player_doc, "other_positions")
	_copy_child_table(trialist_doc.emergency_contacts, player_doc, "emergency_contacts")

	player_doc.insert(ignore_permissions=True)

	trialist_doc.db_set("player", player_doc.name)
	trialist_doc.db_set("status", "Converted to Player")
	trialist_doc.db_set("is_athlete", 1)
	trialist_doc.db_set("converted_on", today())

	return {
		"status": "Success",
		"player": player_doc.name,
	}
