# Copyright (c) 2026, Pep Sports Limited and contributors
# For license information, please see license.txt

"""Hooks into the Healthcare app's Patient Encounter doctype, wired up
via this app's hooks.py (see the doc_events snippet in setup.py's
docstring / the install README). Keeps Trialist.medical_clearance_status
in sync with the doctor's verdict, without this app needing to modify
anything inside the Healthcare app itself.

Relies on two custom fields added onto Patient Encounter by
get_custom_fields() in setup.py:
  - trialist        Link -> Trialist   (which trialist this exam is for)
  - fitness_result   Select "\nFit\nNot Fit"   (the doctor's verdict)
"""

import frappe
from frappe import _
from frappe.utils import today


def validate_patient_encounter(doc, method=None):
	"""Block submission of a trial-medical encounter until the doctor has
	actually recorded a verdict - otherwise on_submit below would have
	nothing to propagate and the trialist would be stuck "Pending"
	forever with no record of why."""

	if doc.get("trialist") and not doc.get("fitness_result"):
		frappe.throw(_("Please record a Fitness Result before submitting this encounter."))


def on_patient_encounter_submit(doc, method=None):
	"""Doctor has submitted the medical exam - propagate the verdict back
	onto the linked Trialist so the sport-specific sections of that form
	unlock (Fit) or stay locked with a clear rejection reason (Not Fit).
	"""

	trialist_name = doc.get("trialist")
	if not trialist_name:
		return

	if not frappe.db.exists("Trialist", trialist_name):
		frappe.log_error(
			title="Sports Complex: medical encounter references missing Trialist",
			message=f"Patient Encounter {doc.name} -> trialist {trialist_name}",
		)
		return

	fitness_result = doc.get("fitness_result")

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
