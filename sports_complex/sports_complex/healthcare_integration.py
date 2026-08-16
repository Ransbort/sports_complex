# Copyright (c) 2026, Pep Sports Limited and contributors
# For license information, please see license.txt

"""Hooks into the Healthcare app's Patient / Patient Encounter doctypes
(and exposes a whitelisted entry point off Patient), wired up via this
app's hooks.py. Keeps the trial-candidacy pipeline in sync with the
doctor's verdict, without this app needing to modify anything inside the
Healthcare app itself.

Registration flow (medical-first — per the team's confirmed redesign):
  1. Medical/front-desk staff pull up (or register) a Patient through
     Healthcare as usual, then click "Register as Trial Candidate" (a
     Client Script button added to the Patient form — see
     make_client_scripts() in setup.py) which calls
     register_trial_candidate() below. That flags the Patient as a trial
     candidate and opens a draft trial medical exam for the doctor's
     worklist — no Trialist exists yet at this point.
  2. The doctor examines them and submits the encounter with a Fitness
     Result. on_patient_encounter_submit() below writes the verdict back
     onto the *Patient* record (not a Trialist — none exists yet).
  3. Once Patient.sc_trial_clearance_status = "Cleared", sports-complex
     staff pull up that Patient by name from the Trialist form's Patient
     picker (see trial_candidate_patient_query() in trialist.py) and
     enter the sport-specific details (dominant foot, playing level,
     previous club, interests, experience). trialist.get_patient_snapshot()
     carries across everything medical/front-desk already captured so it
     isn't re-typed.

A second, narrower path still exists for *re-trialing* someone who
already has a Trialist record (e.g. re-attempting after an injury, or a
previous "Not Fit"/"Not Cleared" result): Trialist.send_to_clinic()
creates the encounter with `trialist` set directly, and
on_patient_encounter_submit() below updates that existing Trialist
instead of the originating Patient.

Relies on custom fields added by get_custom_fields() in setup.py:
  Patient:
    - sc_is_trial_candidate     Check
    - sc_trial_clearance_status Select "\nPending\nCleared\nNot Cleared"
    - sc_trial_cleared_on       Date
    - sc_trial_encounter        Link -> Patient Encounter
    - sc_trialist               Link -> Trialist (set once converted -
                                 see Trialist.after_insert()/on_update())
  Patient Encounter:
    - is_trial_medical_exam     Check (this encounter is a trial screening)
    - trialist                  Link -> Trialist (re-trial path only)
    - fitness_result            Select "\nFit\nNot Fit"
"""

import frappe
from frappe import _
from frappe.utils import today, nowdate, nowtime


def _get_or_create_trial_appointment_type():
	"""Patient Encounter requires an appointment_type, but at
	registration time nobody has booked an actual appointment - any
	doctor at the clinic picks the encounter up. Rather than depend on
	someone having manually created a suitable Appointment Type first,
	provision a dedicated one the first time it's needed.

	Shared by register_trial_candidate() below and
	Trialist.send_to_clinic() (the re-trial path, trialist.py).
	"""
	name = "Trial Medical Exam"
	if not frappe.db.exists("Appointment Type", name):
		frappe.get_doc({
			"doctype": "Appointment Type",
			"appointment_type": name,
		}).insert(ignore_permissions=True)
	return name


@frappe.whitelist()
def register_trial_candidate(patient):
	"""New entry point for the medical-first flow: front desk/medical
	staff call this from the "Register as Trial Candidate" button added
	to the Patient form (see make_client_scripts() in setup.py) once the
	person has already been checked in as a Patient through Healthcare's
	own registration.

	Flags the Patient as a trial candidate and opens a draft Patient
	Encounter for the doctor's worklist — deliberately not navigated to,
	same reasoning as Trialist.send_to_clinic(): the doctor finds it in
	their own Patient Encounter list, there's no reason to route them
	through the sports-complex UI.
	"""
	patient_doc = frappe.get_doc("Patient", patient)

	if patient_doc.get("sc_trialist"):
		frappe.throw(
			_("{0} has already been registered as Trialist {1}.").format(
				patient_doc.patient_name, patient_doc.get("sc_trialist")
			)
		)
	if patient_doc.get("sc_trial_clearance_status") == "Pending":
		frappe.throw(
			_("{0} already has a trial medical exam awaiting the doctor's result.").format(
				patient_doc.patient_name
			)
		)

	encounter = frappe.get_doc({
		"doctype": "Patient Encounter",
		"patient": patient_doc.name,
		"patient_name": patient_doc.patient_name,
		"is_trial_medical_exam": 1,
		"appointment_type": _get_or_create_trial_appointment_type(),
		"encounter_date": nowdate(),
		"encounter_time": nowtime(),
	})
	encounter.insert(ignore_permissions=True)

	patient_doc.db_set({
		"sc_is_trial_candidate": 1,
		"sc_trial_clearance_status": "Pending",
	})

	return {
		"status": "Success",
		"encounter": encounter.name,
	}


def validate_patient_encounter(doc, method=None):
	"""Block submission of a trial-medical encounter until the doctor has
	actually recorded a verdict - otherwise on_submit below would have
	nothing to propagate and the candidate/trialist would be stuck
	"Pending" forever with no record of why."""

	if doc.get("is_trial_medical_exam") and not doc.get("fitness_result"):
		frappe.throw(_("Please record a Fitness Result before submitting this encounter."))


def on_patient_encounter_submit(doc, method=None):
	"""Doctor has submitted the trial medical exam - propagate the
	verdict onto whichever record is actually waiting on it: an existing
	Trialist for a re-trial (doc.trialist set - see
	Trialist.send_to_clinic()), or otherwise the originating Patient
	itself (first-time candidate, medical-first flow - see
	register_trial_candidate() above)."""

	if not doc.get("is_trial_medical_exam"):
		return

	fitness_result = doc.get("fitness_result")
	trialist_name = doc.get("trialist")

	if trialist_name:
		_propagate_to_trialist(doc, trialist_name, fitness_result)
	else:
		_propagate_to_patient(doc, fitness_result)


def _propagate_to_trialist(doc, trialist_name, fitness_result):
	if not frappe.db.exists("Trialist", trialist_name):
		frappe.log_error(
			title="Sports Complex: medical encounter references missing Trialist",
			message=f"Patient Encounter {doc.name} -> trialist {trialist_name}",
		)
		return

	frappe.db.set_value("Trialist", trialist_name, "medical_encounter", doc.name)

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


def _propagate_to_patient(doc, fitness_result):
	"""First-time candidate path - no Trialist exists yet, so the verdict
	(and the encounter that produced it) is recorded on the Patient
	itself. Sports staff pick this Patient up from
	trial_candidate_patient_query() once sc_trial_clearance_status reads
	"Cleared"."""

	patient = doc.patient

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
