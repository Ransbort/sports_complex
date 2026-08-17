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
		self.validate_patient_cleared()

	def after_insert(self):
		if self.patient:
			frappe.db.set_value("Patient", self.patient, "sc_trialist", self.name)

	def on_update(self):
		# Keep Patient.sc_trialist in sync if the linked patient is ever
		# changed after creation - shouldn't normally happen (the form
		# only lets you pick a patient before the first save, see
		# trialist.js), but safer than leaving a stale reverse-link if it
		# ever is.
		before = self.get_doc_before_save()
		if not before or before.patient == self.patient:
			return
		if before.patient:
			frappe.db.set_value("Patient", before.patient, "sc_trialist", None)
		if self.patient:
			frappe.db.set_value("Patient", self.patient, "sc_trialist", self.name)

	def set_full_name(self):
		self.full_name = " ".join(
			part for part in [self.first_name, self.middle_name, self.last_name] if part
		).strip()

	def set_age(self):
		self.age = _format_age(self.date_of_birth)

	def validate_patient_cleared(self):
		"""Server-side safety net for the medical-first flow: the Patient
		picker (trial_candidate_patient_query() below, wired up in
		trialist.js) only lists cleared, not-yet-converted patients, but
		that's a UI-level filter only - someone could still set/change
		`patient` directly (API, data import, editing a draft). Block
		save if it doesn't actually point at a cleared, unconverted
		Patient - a Trialist should never exist without a doctor having
		signed off first.

		Only enforced when `patient` is being newly set (new record) or
		changed on an existing one - NOT on every ordinary re-save. A
		re-trial can leave the linked Patient's sc_trial_clearance_status
		sitting at "Pending" for a while (new medical exam in progress);
		without this guard, simply opening and saving the existing
		Trialist during that window would incorrectly throw, even though
		nothing about the Patient link itself changed.
		"""
		if not self.patient:
			return

		if not self.is_new():
			before = self.get_doc_before_save()
			if before and before.patient == self.patient:
				return

		row = frappe.db.get_value(
			"Patient", self.patient, ["sc_trial_clearance_status", "sc_trialist"], as_dict=True
		)
		if not row:
			frappe.throw(_("Patient {0} not found.").format(self.patient))

		if row.sc_trial_clearance_status != "Cleared":
			frappe.throw(
				_("Patient {0} has not been medically cleared for trials (status: {1}).").format(
					self.patient, row.sc_trial_clearance_status or _("Not a trial candidate")
				)
			)
		if row.sc_trialist and row.sc_trialist != self.name:
			frappe.throw(
				_("Patient {0} is already registered as Trialist {1}.").format(self.patient, row.sc_trialist)
			)


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
	until a doctor has cleared this trialist. Under the medical-first
	flow this is already true the moment the Trialist is created (see
	validate_patient_cleared() above, which refuses to save a Trialist
	against an un-cleared Patient) - this guard mainly matters for the
	re-trial path, where medical_clearance_status can regress to
	"Not Cleared"/"Pending" after a re-trial check-in (Front Desk,
	Appointment Type "Trialist" - see healthcare_integration.py) puts a
	fresh medical exam in progress."""
	if trialist_doc.medical_clearance_status != "Cleared":
		frappe.throw(
			_(
				"Trialist {0} has not been medically cleared yet (status: {1}). "
				"Send them to the clinic and wait for the doctor's clearance "
				"before registering them as a Player."
			).format(trialist_doc.name, trialist_doc.medical_clearance_status or _("Not Sent"))
		)


@frappe.whitelist()
def get_patient_snapshot(patient):
	"""Pre-fill a new Trialist form from an already medically-cleared
	Patient - see healthcare_integration.py's on_patient_encounter_submit()
	for how a Patient gets to "Cleared" in the first place. Sports staff
	pick the Patient (searchable by name,
	see trial_candidate_patient_query() below) once medical has cleared
	them; this carries across the general info medical/front-desk already
	captured so it isn't re-typed.

	Gender note: Patient.sex is a Link to the Gender doctype and can hold
	whatever a site has configured there, while Trialist.gender is a
	fixed Select (Male/Female/Other) - only copied across when it's one
	of those three exact values, otherwise left blank for the operator to
	set rather than risking a "not a valid option" error on save.

	known_allergies/chronic_medical_conditions/previous_surgeries/
	current_medications/previous_serious_injuries all come from the
	Patient's trial medical encounter (Patient.sc_trial_encounter), not
	the Patient doctype's own allergies/medication fields - the doctor
	records all five on the Patient Encounter during the trial-medical
	exam itself (see healthcare_integration.py's
	TRIAL_ONLY_ENCOUNTER_FIELDS), so a Patient who's never been through
	one has nothing to carry across yet.
	"""
	patient_doc = frappe.get_doc("Patient", patient)

	if patient_doc.get("sc_trial_clearance_status") != "Cleared":
		frappe.throw(
			_("{0} has not been medically cleared for trials yet (status: {1}).").format(
				patient_doc.patient_name, patient_doc.get("sc_trial_clearance_status") or _("Not a trial candidate")
			)
		)

	existing_trialist = patient_doc.get("sc_trialist")
	if existing_trialist:
		frappe.throw(
			_("{0} is already registered as Trialist {1}.").format(patient_doc.patient_name, existing_trialist)
		)

	gender = patient_doc.sex if patient_doc.sex in ("Male", "Female", "Other") else None

	encounter_name = patient_doc.get("sc_trial_encounter")
	encounter_history = (
		frappe.db.get_value(
			"Patient Encounter",
			encounter_name,
			[
				"known_allergies",
				"chronic_medical_conditions",
				"previous_surgeries",
				"current_medications",
				"previous_serious_injuries",
			],
			as_dict=True,
		)
		if encounter_name
		else None
	) or {}

	return {
		"first_name": patient_doc.first_name,
		"last_name": patient_doc.last_name,
		"gender": gender,
		"date_of_birth": patient_doc.dob,
		"mobile_number": patient_doc.mobile,
		"email": patient_doc.email,
		# Not a real identification document - Patient.uid is this
		# person's internal Healthcare record ID, not a passport/national
		# ID/etc. Tag it as such via identification_type rather than
		# dropping it into identification_number unlabeled (which used to
		# read as if it were a real ID number). Sports staff can still
		# overwrite both fields with an actual document once/if the
		# trialist provides one.
		"identification_type": "Patient UID",
		"identification_number": patient_doc.get("uid"),
		"known_allergies": encounter_history.get("known_allergies"),
		"chronic_medical_conditions": encounter_history.get("chronic_medical_conditions"),
		"current_medications": encounter_history.get("current_medications"),
		"previous_surgeries": encounter_history.get("previous_surgeries"),
		"previous_serious_injuries": encounter_history.get("previous_serious_injuries"),
		"medical_clearance_status": patient_doc.get("sc_trial_clearance_status"),
		"medical_cleared_on": patient_doc.get("sc_trial_cleared_on"),
		"medical_encounter": patient_doc.get("sc_trial_encounter"),
	}


@frappe.whitelist()
def get_patient_uid(patient):
	"""Returns just this Patient's own uid - nothing else off the Patient
	record. Used by trialist.js to re-sync Identification Number whenever
	Identification Type is (re-)selected as "Patient UID" after the
	operator has changed it to something else (e.g. picked "Passport",
	typed a number, then switched back) - get_patient_snapshot() above
	only ever runs once, at Patient-pick time, so without this the two
	fields could end up mismatched (Type says "Patient UID" but Number
	still holds whatever was last typed).

	A narrow wrapper, same reasoning as healthcare_integration.
	get_trial_appointment_type_for_client() - exposes one non-sensitive
	value without requiring the caller to have read access to the Patient
	doctype itself (sports staff generally don't - see
	trial_candidate_patient_query() below for why a raw SQL query is used
	there rather than a permitted Link query, and get_patient_snapshot()
	above for the same reasoning applied to the full pre-fill).
	"""
	return frappe.db.get_value("Patient", patient, "uid")


@frappe.whitelist()
def trial_candidate_patient_query(doctype, txt, searchfield, start, page_len, filters):
	"""Link-field query for Trialist.patient (wired up in trialist.js) -
	only surfaces Patients who are medically cleared and not yet
	converted to a Trialist, so sports staff can't accidentally pick
	someone who hasn't been through medicals, or register the same
	person twice.
	"""
	return frappe.db.sql(
		"""
		SELECT name, patient_name
		FROM `tabPatient`
		WHERE sc_trial_clearance_status = 'Cleared'
			AND (sc_trialist IS NULL OR sc_trialist = '')
			AND (name LIKE %(txt)s OR patient_name LIKE %(txt)s)
		ORDER BY patient_name
		LIMIT %(page_len)s OFFSET %(start)s
		""",
		{"txt": f"%{txt}%", "start": start, "page_len": page_len},
	)


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
