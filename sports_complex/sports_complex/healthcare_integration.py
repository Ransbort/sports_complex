# Copyright (c) 2026, Pep Sports Limited and contributors
# For license information, please see license.txt

"""Hooks into the Healthcare app's Patient Appointment / Patient Encounter
doctypes, wired up via this app's hooks.py. Keeps the trial-candidacy
pipeline in sync with the doctor's verdict, without this app needing to
modify anything inside the Healthcare app itself — including Front Desk
(healthcare/page/front_desk/front_desk.py), which stays completely
untouched.

Registration flow (medical-first, per the team's confirmed redesign):
  1. A person enters the pipeline the moment ANY Patient Appointment gets
     created for them with Appointment Type = the site's configured Trial
     Appointment Type (Sports Complex Setup > Trials, defaults to
     "Trialist" — see get_trial_appointment_type() below) — a walk-in
     check-in or a pre-booked appointment, first exam or a re-trial, it's
     all the exact same mechanism now. Front Desk's own check-in flow
     (checkin/queue/nurse/doctor tabs) is used as-is; nothing sports-
     specific needs to exist there. on_patient_appointment_after_insert()
     below reacts to that and flags the Patient as a trial candidate.
  2. The person goes through Front Desk's normal queue - Nurse Station
     takes vitals, then the doctor calls start_consultation(), which
     creates the actual Patient Encounter and inherits appointment_type
     from the appointment automatically (see front_desk.py - no changes
     needed there for this to work). The doctor records a Fitness Result
     and submits.
  3. on_patient_encounter_submit() below reads that verdict. It always
     updates the originating Patient's own trial-candidacy fields; if
     that Patient already has a registered Trialist (sc_trialist set —
     i.e. this was a *re-trial*, not a first exam), it also propagates
     the verdict onto that existing Trialist record the same way it
     always has.
  4. Once Patient.sc_trial_clearance_status = "Cleared", sports-complex
     staff pull up that Patient by name from the Trialist form's Patient
     picker (see trial_candidate_patient_query() in trialist.py) and
     enter the sport-specific details (dominant foot, playing level,
     previous club, interests, experience) — trialist.get_patient_snapshot()
     carries across everything already captured so it isn't re-typed.

There is deliberately only ONE mechanism for both a first-time exam and a
re-trial (e.g. re-attempting after injury, or a previous "Not Fit"/
"Not Cleared" result): check the person in again with the configured Trial
Appointment Type. Whether that's a first exam or a re-trial is derived from
whether the Patient already has a Trialist (sc_trialist) at verdict time —
nothing needs to be chosen up front.

Relies on custom fields added by get_custom_fields() in setup.py:
  Patient:
    - sc_is_trial_candidate     Check
    - sc_trial_clearance_status Select "\nPending\nCleared\nNot Cleared"
    - sc_trial_cleared_on       Date
    - sc_trial_encounter        Link -> Patient Encounter
    - sc_trialist               Link -> Trialist (set once converted -
                                 see Trialist.after_insert()/on_update())
  Patient Encounter:
    - sc_trial_tab                  Tab Break ("Trial Medical Exam")
    - trialist                      Link -> Trialist (auto-set, informational
                                     only — see _propagate_to_trialist() below)
    - fitness_result                Select "\nFit\nNot Fit"
    - fitness_notes                 Small Text (doctor's reasoning behind
                                     Fitness Result)
    - known_allergies               Small Text (pre-filled from Patient.
                                     allergies on creation - see
                                     sync_trial_medical_history_from_patient()
                                     below)
    - chronic_medical_conditions    Small Text
    - previous_surgeries            Small Text
    - current_medications           Small Text (pre-filled from Patient.
                                     medication on creation, same as
                                     known_allergies above)
    - previous_serious_injuries     Small Text
      (all eight fields above live together under the sc_trial_tab Tab
      Break; the five Medical Information fields are captured by the
      doctor alongside the Fitness Result during a trial-medical
      encounter, and carried across onto the new Trialist by
      get_patient_snapshot() in trialist.py)

...plus the "trial_appointment_type" field on the Sports Complex Setup
single doctype (Trials tab), and two things auto-provisioned by
install.py's after_install/after_migrate so nobody has to create them by
hand first:
  - the Appointment Type record itself, via ensure_trial_appointment_type()
  - a Client Script on Patient Encounter's Form view, via
    ensure_fitness_result_visibility_script(), that hides the whole
    "Trial Medical Exam" tab (sc_trial_tab, Fitness Result, Fitness
    Assessment Notes, and the five Medical Information fields above —
    TRIAL_ONLY_ENCOUNTER_FIELDS) entirely unless the open encounter's
    Appointment Type matches
    get_trial_appointment_type() — doctors doing an ordinary (non-trial)
    consultation never see a tab that means nothing to them.
"""

import json

import frappe
from frappe import _
from frappe.utils import today

# Used only if Sports Complex Setup's Trial Appointment Type field has
# never been set (e.g. a brand new site before Setup has been opened
# once) - get_trial_appointment_type() below is what everything else in
# this module actually calls.
DEFAULT_TRIAL_APPOINTMENT_TYPE = "Trialist"


def get_trial_appointment_type():
	"""The Appointment Type that marks a Patient Appointment (and, once
	start_consultation() inherits it, the resulting Patient Encounter) as
	part of the trial pipeline. Configurable per site via Sports Complex
	Setup > Trials > Trial Appointment Type (falls back to "Trialist" if
	that's ever left blank). frappe.get_cached_doc() means this is cheap
	to call from every hook below rather than threading the value through
	as a parameter.
	"""
	settings = frappe.get_cached_doc("Sports Complex Setup")
	return settings.get("trial_appointment_type") or DEFAULT_TRIAL_APPOINTMENT_TYPE


def ensure_trial_appointment_type():
	"""Idempotently provision whichever Appointment Type is currently
	configured in Sports Complex Setup (default "Trialist") so it shows
	up in Front Desk's Appointment Type picker out of the box. Called
	from sports_complex.install (after_install/after_migrate) — safe to
	call repeatedly, and re-provisions correctly if the configured name
	is changed later (rename in Setup, then bench migrate).
	"""
	appointment_type = get_trial_appointment_type()
	if not frappe.db.exists("Appointment Type", appointment_type):
		frappe.get_doc({
			"doctype": "Appointment Type",
			"appointment_type": appointment_type,
		}).insert(ignore_permissions=True)


@frappe.whitelist()
def get_trial_appointment_type_for_client():
	"""Read-only wrapper around get_trial_appointment_type() for the
	Fitness Result visibility Client Script below - any logged-in user
	can call this (e.g. a Healthcare Practitioner filling in a Patient
	Encounter), even without read access to Sports Complex Setup itself,
	which is deliberately locked down to System Manager / Sports Complex
	Manager (payment gateway config, tax templates, etc. live there too).
	This only ever exposes the one non-sensitive value the client script
	needs, nothing else from Setup.
	"""
	return get_trial_appointment_type()


# Client Script content is intentionally kept as a plain string (not a
# separate .js file) since it has to be pushed into the DB via
# ensure_fitness_result_visibility_script() below rather than loaded as a
# static asset - Patient Encounter belongs to the Healthcare app, and this
# app deliberately never edits Healthcare's own files (see this module's
# top docstring). The marker comment lets ensure_fitness_result_visibility_script()
# find and update its own record on every bench migrate without touching
# any other Client Script someone might separately add for this same
# dt+view (Frappe runs every enabled Client Script for a given dt+view,
# not just one, so there's no conflict either way).
#
# Covers the whole "Trial Medical Exam" Tab Break (sc_trial_tab) plus
# fitness_result, fitness_notes, and the five Medical Information fields
# (known_allergies, chronic_medical_conditions, previous_surgeries,
# current_medications, previous_serious_injuries) added alongside it in
# setup.get_custom_fields() - none of them mean anything outside a
# trial-medical encounter, so all eight are toggled together. Toggling the
# Tab Break itself hides the tab entirely rather than leaving an empty one
# in the tab bar; the individual fields are toggled too, defensively, in
# case a future Frappe version ever renders a hidden tab's fields some
# other way.
TRIAL_ONLY_ENCOUNTER_FIELDS = [
	"sc_trial_tab",
	"fitness_result",
	"fitness_notes",
	"known_allergies",
	"chronic_medical_conditions",
	"previous_surgeries",
	"current_medications",
	"previous_serious_injuries",
]

FITNESS_RESULT_VISIBILITY_SCRIPT = (
	"""// __sports_complex_fitness_result_visibility__
// Managed by sports_complex.sports_complex.healthcare_integration.
// ensure_fitness_result_visibility_script() - re-applied on every bench
// migrate. Edit the logic below if needed, but keep the marker comment
// above intact so that function can keep finding this record.
//
// Fitness Result and the trial-only history fields below only mean
// something for a trial-medical encounter, so hide them entirely for
// every other Appointment Type - fewer fields for doctors doing ordinary
// consultations to puzzle over.

var SPORTS_COMPLEX_TRIAL_ONLY_FIELDS = """
	+ json.dumps(TRIAL_ONLY_ENCOUNTER_FIELDS)
	+ """;

frappe.ui.form.on("Patient Encounter", {
	refresh: function (frm) {
		sports_complex_toggle_trial_fields(frm);
	},
	appointment_type: function (frm) {
		sports_complex_toggle_trial_fields(frm);
	},
});

function sports_complex_toggle_trial_fields(frm) {
	var present = SPORTS_COMPLEX_TRIAL_ONLY_FIELDS.filter(function (fieldname) {
		return !!frm.fields_dict[fieldname];
	});
	if (!present.length) {
		return;
	}
	frappe.call({
		method: "sports_complex.sports_complex.healthcare_integration.get_trial_appointment_type_for_client",
		callback: function (r) {
			var configured = r.message || "Trialist";
			var show = !!frm.doc.appointment_type && frm.doc.appointment_type === configured;
			present.forEach(function (fieldname) {
				frm.toggle_display(fieldname, show);
			});
		},
	});
}
"""
)


def ensure_fitness_result_visibility_script():
	"""Idempotently create/update the Client Script that hides Patient
	Encounter's Fitness Result field (and the five Medical Information
	fields alongside it — see TRIAL_ONLY_ENCOUNTER_FIELDS above) unless the
	encounter's Appointment Type matches get_trial_appointment_type() (see
	FITNESS_RESULT_VISIBILITY_SCRIPT above). Called from
	sports_complex.install (after_install/after_migrate) — safe to call
	repeatedly; matches on the marker comment inside the script content
	rather than just dt+view, so re-running this never clobbers some
	other, unrelated Client Script someone later adds for Patient
	Encounter's Form view.
	"""
	marker = "__sports_complex_fitness_result_visibility__"
	existing_name = frappe.db.get_value(
		"Client Script",
		{"dt": "Patient Encounter", "view": "Form", "script": ("like", f"%{marker}%")},
	)
	if existing_name:
		doc = frappe.get_doc("Client Script", existing_name)
		doc.script = FITNESS_RESULT_VISIBILITY_SCRIPT
		doc.enabled = 1
		doc.save(ignore_permissions=True)
	else:
		frappe.get_doc({
			"doctype": "Client Script",
			# Client Script is a "Set by user" (Prompt) autoname doctype -
			# Frappe won't generate a name on its own, so one must be
			# supplied here or insert() raises "Please set the document
			# name". Fixed and descriptive so re-running this after a
			# manual deletion recreates the same record name.
			"name": "Sports Complex Fitness Result Visibility",
			"dt": "Patient Encounter",
			"view": "Form",
			"enabled": 1,
			"script": FITNESS_RESULT_VISIBILITY_SCRIPT,
		}).insert(ignore_permissions=True)


def on_patient_appointment_after_insert(doc, method=None):
	"""A Patient Appointment has just been created with the configured
	Trial Appointment Type — whether that's Front Desk's walk-in check-in
	(create_walkin_checkin()) or a pre-booked appointment
	(create_consultation()), and whether this Patient has never trialed
	before or is re-attempting, doesn't matter here: either way, they're
	now mid-exam. on_patient_encounter_submit() below is what actually
	tells first-timers and re-trials apart, once there's a verdict to
	propagate.
	"""
	if doc.appointment_type != get_trial_appointment_type() or not doc.patient:
		return

	frappe.db.set_value(
		"Patient",
		doc.patient,
		{
			"sc_is_trial_candidate": 1,
			"sc_trial_clearance_status": "Pending",
		},
	)


def sync_trial_medical_history_from_patient(doc, method=None):
	"""Pre-fill the trial-only Known Allergies / Current Medications fields
	(see TRIAL_ONLY_ENCOUNTER_FIELDS above) from the Patient's own,
	already-existing Allergies/Medication fields (Healthcare core - see
	patient.json's "Allergies, Medical and Surgical History" section) the
	moment a trial-medical Patient Encounter is created.

	Hooked to "before_insert" specifically, not "validate" - this is a
	one-time copy taken at encounter-creation time, not a live mirror.
	Using before_insert means it only ever runs once per encounter, so a
	doctor editing either field afterwards (e.g. to note something the
	trial exam turned up that isn't on the Patient's general record yet)
	is never clobbered by a later save - and nothing here is ever written
	back onto the Patient record either, in either direction.

	Deliberately also fires when the encounter is built via
	frappe.get_doc({...}).insert() from Python (start_consultation() in
	front_desk.py, not touched by this app) rather than through the form
	UI, unlike Frappe's client-side "fetch_from" field property, which
	only ever fires from a browser interaction and would silently do
	nothing for encounters created this way.
	"""
	if doc.appointment_type != get_trial_appointment_type() or not doc.patient:
		return

	allergies, medication = frappe.db.get_value("Patient", doc.patient, ["allergies", "medication"])
	doc.known_allergies = allergies
	doc.current_medications = medication


def validate_patient_encounter(doc, method=None):
	"""Block *submission* of a trial-medical encounter until the doctor has
	actually recorded a verdict - otherwise on_submit below would have
	nothing to propagate and the candidate/trialist would be stuck
	"Pending" forever with no record of why.

	"validate" fires on every save, not just submit - including the very
	first insert() that start_consultation() in front_desk.py does to
	create the encounter in the first place (docstatus 0, no verdict yet
	by definition). Only enforce this once the doctor is actually
	submitting (docstatus 1) - Frappe sets docstatus to 1 before running
	validate() on submit() - otherwise the encounter could never even be
	created/saved as a draft for the doctor to fill in.
	"""

	if doc.docstatus != 1:
		return

	if doc.appointment_type == get_trial_appointment_type() and not doc.get("fitness_result"):
		frappe.throw(_("Please record a Fitness Result before submitting this encounter."))


def on_patient_encounter_submit(doc, method=None):
	"""Doctor has submitted a trial-medical exam - propagate the verdict.
	Always updates the originating Patient's own trial-candidacy fields
	(the single source of truth); additionally propagates onto an
	existing Trialist record too, if this Patient already has one — that
	condition is what distinguishes a re-trial from a first exam, not
	anything chosen at check-in time.
	"""

	if doc.appointment_type != get_trial_appointment_type():
		return

	fitness_result = doc.get("fitness_result")
	patient = doc.patient

	_propagate_to_patient(doc, patient, fitness_result)

	existing_trialist = frappe.db.get_value("Patient", patient, "sc_trialist")
	if existing_trialist:
		_propagate_to_trialist(doc, existing_trialist, fitness_result)


def _propagate_to_patient(doc, patient, fitness_result):
	frappe.db.set_value("Patient", patient, "sc_trial_encounter", doc.name)

	if fitness_result == "Fit":
		frappe.db.set_value(
			"Patient",
			patient,
			{
				"sc_trial_clearance_status": "Cleared",
				"sc_trial_cleared_on": today(),
			},
		)
		frappe.publish_realtime(
			event="trial_candidate_medically_cleared",
			message={
				"patient": patient,
				"patient_name": doc.patient_name,
				"message": _("{0} is medically cleared - ready for sports registration").format(doc.patient_name),
			},
		)
	elif fitness_result == "Not Fit":
		frappe.db.set_value("Patient", patient, "sc_trial_clearance_status", "Not Cleared")


def _propagate_to_trialist(doc, trialist_name, fitness_result):
	"""Re-trial path: this Patient already has a registered Trialist, so
	the verdict also needs to land on that record directly (its own
	medical_clearance_status/medical_cleared_on drive the "Mark as
	Player" button and the Playing Profile/Trial Details sections — see
	trialist.js/trialist.json — independently of the Patient's fields).
	"""
	if not frappe.db.exists("Trialist", trialist_name):
		frappe.log_error(
			title="Sports Complex: medical encounter references missing Trialist",
			message=f"Patient Encounter {doc.name} -> trialist {trialist_name} (via patient {doc.patient})",
		)
		return

	frappe.db.set_value("Trialist", trialist_name, "medical_encounter", doc.name)
	# Auto-set, informational only (see this module's docstring) - lets
	# someone looking at the Patient Encounter see which Trialist it
	# ended up updating, without requiring anyone to have set it by hand.
	frappe.db.set_value("Patient Encounter", doc.name, "trialist", trialist_name)

	if fitness_result == "Fit":
		frappe.db.set_value(
			"Trialist",
			trialist_name,
			{
				"medical_clearance_status": "Cleared",
				"medical_cleared_on": today(),
			},
		)
		frappe.publish_realtime(
			event="trialist_medical_cleared",
			message={"trialist": trialist_name, "message": _("Medically cleared - ready for final registration")},
		)
	elif fitness_result == "Not Fit":
		frappe.db.set_value(
			"Trialist",
			trialist_name,
			{
				"medical_clearance_status": "Not Cleared",
				"status": "Rejected",
			},
		)