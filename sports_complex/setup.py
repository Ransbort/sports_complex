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
		],
		# Medical-clearance flow: Trialist.send_to_clinic() creates a
		# Patient and hands off to a fresh Patient Encounter for the
		# doctor to complete. These two fields are what let
		# healthcare_integration.py trace that submitted encounter back
		# to the trialist and read the doctor's verdict.
		#
		# fitness_result is required (see
		# healthcare_integration.validate_patient_encounter) whenever
		# trialist is set, so a medical encounter can't be submitted
		# without an actual verdict for on_submit to propagate.
		"Patient Encounter": [
			{
				"fieldname": "trialist",
				"label": "Trialist",
				"fieldtype": "Link",
				"options": "Trialist",
				"insert_after": "appointment_type",
				"reqd": 0,
				"hidden": 0,
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
		],
	}
