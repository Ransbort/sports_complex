# isort: skip_file
"""Custom-field install/uninstall logic for sports_complex.

Wired into sports_complex.install (after_install / after_migrate) and
sports_complex.uninstall (before_uninstall) — see those files.
"""
import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def make_custom_fields(update=True):
	custom_fields = get_custom_fields()
	create_custom_fields(custom_fields, update=update)


def delete_custom_fields(custom_fields: dict):
	"""
	:param custom_fields: a dict like `{'Sales Invoice': [{fieldname: '', ...}]}`
	"""
	for doctype, fields in custom_fields.items():
		frappe.db.delete(
			"Custom Field",
			{
				"fieldname": ("in", [field["fieldname"] for field in fields]),
				"dt": doctype,
			},
		)
		frappe.clear_cache(doctype=doctype)


def get_custom_fields():
	return {
		# Placed inside the app's existing "SC Source" group (see
		# fixtures/custom_field.json: facility_booking, membership,
		# tournament_registration, training_session, equipment_issue,
		# equipment_return) rather than a new section — two more
		# source-doctype links in that same family, for invoices raised
		# against a Trialist or Player.
		"Sales Invoice": [
			{
				"fieldname": "trialist",
				"label": "Trialist",
				"fieldtype": "Link",
				"options": "Trialist",
				"insert_after": "equipment_return",
				"reqd": 0,
				"hidden": 0,
			},
			{
				"fieldname": "player",
				"label": "Player",
				"fieldtype": "Link",
				"options": "Player",
				"insert_after": "trialist",
				"reqd": 0,
				"hidden": 0,
			},
			{
				"fieldname": "player_session",
				"label": "Player Session",
				"fieldtype": "Link",
				"options": "Player Session",
				"insert_after": "player",
				"reqd": 0,
				"hidden": 0,
				"description": "Set when this invoice was raised for a \"Book a Player\" booking - the private/1-on-1 session with a roster Player, not the coach-booking flow (see the training_session field above for that).",
			},
		],
		# Medical-first trial candidacy flow (see healthcare_integration.py
		# for the full picture). The Patient is the entry point now: a
		# person becomes a "trial candidate" on the *Patient* record when
		# medical/front-desk staff register them for a trial medical exam,
		# well before any Trialist exists. These fields track that pipeline
		# directly on Patient so the Trialist doctype never has to be
		# created (and never has to guess at a Trial Batch) before a doctor
		# has actually cleared the person.
		"Patient": [
			{
				"fieldname": "sc_trial_section",
				"label": "Trial Candidacy (Sports Complex)",
				"fieldtype": "Section Break",
				"insert_after": "user_id",
				"collapsible": 1,
			},
			{
				"fieldname": "sc_is_trial_candidate",
				"label": "Trial Candidate",
				"fieldtype": "Check",
				"insert_after": "sc_trial_section",
				"reqd": 0,
				"hidden": 0,
				"description": "Ticked automatically the moment a Patient Appointment is created for this person with Appointment Type \"Trialist\" (Front Desk check-in - walk-in or pre-booked).",
			},
			{
				"fieldname": "sc_trial_clearance_status",
				"label": "Trial Clearance Status",
				"fieldtype": "Select",
				"options": "\nPending\nCleared\nNot Cleared",
				"insert_after": "sc_is_trial_candidate",
				"reqd": 0,
				"hidden": 0,
				"read_only": 1,
				"description": "Set automatically once the doctor submits the trial medical exam (Fitness Result).",
			},
			{
				"fieldname": "column_break_sc_trial",
				"fieldtype": "Column Break",
				"insert_after": "sc_trial_clearance_status",
			},
			{
				"fieldname": "sc_trial_cleared_on",
				"label": "Trial Cleared On",
				"fieldtype": "Date",
				"insert_after": "column_break_sc_trial",
				"reqd": 0,
				"hidden": 0,
				"read_only": 1,
			},
			{
				"fieldname": "sc_trial_encounter",
				"label": "Trial Medical Encounter",
				"fieldtype": "Link",
				"options": "Patient Encounter",
				"insert_after": "sc_trial_cleared_on",
				"reqd": 0,
				"hidden": 0,
				"read_only": 1,
			},
			{
				"fieldname": "sc_trialist",
				"label": "Registered Trialist",
				"fieldtype": "Link",
				"options": "Trialist",
				"insert_after": "sc_trial_encounter",
				"reqd": 0,
				"hidden": 0,
				"read_only": 1,
				"description": "Set once sports-complex staff register this cleared patient as a Trialist - prevents duplicate registration.",
			},
		],
		# Medical-first flow (see healthcare_integration.py's module
		# docstring): a Patient Appointment whose Appointment Type
		# matches Sports Complex Setup's configured Trial Appointment
		# Type (default "Trialist") is what puts someone in the
		# pipeline, for both a first exam and a re-trial alike - no
		# separate entry point or dedicated flag needed here.
		# start_consultation() in front_desk.py (unmodified) already
		# inherits appointment_type from the appointment onto the
		# resulting Patient Encounter, so healthcare_integration.py's
		# pipeline logic just reads doc.appointment_type directly.
		#
		# fitness_result is required (see
		# healthcare_integration.validate_patient_encounter) whenever
		# appointment_type is the configured Trial Appointment Type, so a
		# trial encounter can't be submitted without an actual verdict
		# for on_submit to propagate.
		"Patient Encounter": [
			# Own Tab Break, same convention core Healthcare already uses
			# for "Encounter Details"/"Notes" (see patient_encounter.json)
			# - keeps every trial-only field below out of the doctor's way
			# on an ordinary consultation instead of crowding the main
			# tab. Hidden as a whole (not just field-by-field) by
			# healthcare_integration.ensure_fitness_result_visibility_script()
			# unless appointment_type matches the configured Trial
			# Appointment Type.
			{
				"fieldname": "sc_trial_tab",
				"label": "Trial Medical Exam",
				"fieldtype": "Tab Break",
				"insert_after": "appointment_type",
				"hidden": 0,
			},
			{
				"fieldname": "trialist",
				"label": "Trialist",
				"fieldtype": "Link",
				"options": "Trialist",
				"insert_after": "sc_trial_tab",
				"reqd": 0,
				"hidden": 0,
				"read_only": 1,
				"description": "Auto-set on submit if this Patient already has a registered Trialist (i.e. this was a re-trial) - informational only, nothing to fill in here.",
			},
			{
				"fieldname": "fitness_result",
				"label": "Fitness Result",
				"fieldtype": "Select",
				"options": "\nFit\nNot Fit",
				"insert_after": "trialist",
				"reqd": 0,
				"hidden": 0,
			},
			# Doctor's free-text reasoning behind the Fitness Result above.
			{
				"fieldname": "fitness_notes",
				"label": "Fitness Assessment Notes",
				"fieldtype": "Small Text",
				"insert_after": "fitness_result",
				"reqd": 0,
				"hidden": 0,
				"allow_on_submit": 1,
				"description": "Doctor's notes on why the trialist was marked Fit or Not Fit.",
			},
			# These five, together with fitness_result/fitness_notes above, are only
			# ever shown to the doctor when appointment_type matches the
			# configured Trial Appointment Type - see
			# healthcare_integration.ensure_fitness_result_visibility_script()
			# for the Client Script that toggles the whole tab. Captured
			# here (rather than only ever living as free text on
			# Trialist) so the trial-medical exam's findings get carried
			# across automatically and consistently when the Patient is
			# later registered as a Trialist - see
			# trialist.get_patient_snapshot(). Same field order as
			# Trialist's own Medical Information section (see
			# trialist.json).
			#
			# known_allergies/current_medications aren't free-typed from
			# scratch: healthcare_integration.sync_trial_medical_history_
			# from_patient() (before_insert hook) copies them in from the
			# Patient's own, already-existing Allergies/Medication fields
			# (Healthcare core - see patient.json) the moment a
			# trial-medical encounter is created, so the doctor sees
			# what's already on file rather than retyping it. That's a
			# one-time copy, not a live mirror - editing either field here
			# afterwards is never overwritten by a later save, and never
			# writes back to the Patient record either.
			#
			# All five carry "allow_on_submit": 1 - Patient Encounter is
			# normally locked after the doctor submits (that's what makes
			# on_patient_encounter_submit() a reliable one-shot trigger for
			# fitness_result specifically, which deliberately does NOT get
			# this flag - a post-submit edit there wouldn't re-propagate
			# to Patient/Trialist and would leave the recorded verdict and
			# what actually happened out of sync). These five are just
			# documentation though, with nothing downstream keyed off a
			# one-time submit event, so there's no reason a doctor
			# couldn't correct/add to them afterwards - and without this
			# flag, trying to would fail validation.
			{
				"fieldname": "known_allergies",
				"label": "Known Allergies",
				"fieldtype": "Small Text",
				"insert_after": "fitness_notes",
				"reqd": 0,
				"hidden": 0,
				"allow_on_submit": 1,
				"description": "Pre-filled from the Patient's own Allergies field when this encounter is created - edit here if it needs updating.",
			},
			{
				"fieldname": "chronic_medical_conditions",
				"label": "Chronic Medical Conditions",
				"fieldtype": "Small Text",
				"insert_after": "known_allergies",
				"reqd": 0,
				"hidden": 0,
				"allow_on_submit": 1,
			},
			{
				"fieldname": "previous_surgeries",
				"label": "Previous Surgeries",
				"fieldtype": "Small Text",
				"insert_after": "chronic_medical_conditions",
				"reqd": 0,
				"hidden": 0,
				"allow_on_submit": 1,
			},
			{
				"fieldname": "current_medications",
				"label": "Current Medications",
				"fieldtype": "Small Text",
				"insert_after": "previous_surgeries",
				"reqd": 0,
				"hidden": 0,
				"allow_on_submit": 1,
				"description": "Pre-filled from the Patient's own Medication field when this encounter is created - edit here if it needs updating.",
			},
			{
				"fieldname": "previous_serious_injuries",
				"label": "Previous Serious Injuries",
				"fieldtype": "Small Text",
				"insert_after": "current_medications",
				"reqd": 0,
				"hidden": 0,
				"allow_on_submit": 1,
			},
		],
		# Predetermined trial-lab pipeline (see healthcare_integration.py's
		# module docstring, "Lab stage" section, and
		# create_trial_lab_panel()/route_trial_after_vitals() below it).
		# sc_trial_appointment is what lets us ask "which Lab Tests belong
		# to this trialist's visit" - Lab Test has no such link out of the
		# box (its only encounter-side link is the optional `prescription`
		# field, which doesn't exist yet at the point these get created -
		# no Patient Encounter exists until the doctor starts the
		# consultation, same reason Vital Signs links via `appointment`
		# rather than `encounter` - see front_desk.py's save_vitals()).
		"Lab Test": [
			{
				"fieldname": "sc_trial_appointment",
				"label": "Trial Appointment",
				"fieldtype": "Link",
				"options": "Patient Appointment",
				"insert_after": "patient",
				"reqd": 0,
				"hidden": 0,
				"read_only": 1,
				"no_copy": 1,
				"in_standard_filter": 1,
				"search_index": 1,
				"description": "Auto-set when this Lab Test was auto-created as part of a trialist's predetermined lab panel (see Sports Complex Setup > Trials > Required Lab Tests). Blank for every ordinary lab request.",
			},
		],
	}