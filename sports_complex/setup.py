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
				"description": "Ticked automatically when this person is registered for a trial medical exam - see the Sports Complex app's \"Register as Trial Candidate\" button.",
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
		# Medical-clearance flow: register_trial_candidate() in
		# healthcare_integration.py opens a draft Patient Encounter for a
		# first-time trial candidate (no Trialist yet); Trialist.send_to_clinic()
		# does the same for a re-trial, but with `trialist` set. These
		# fields are what let healthcare_integration.py tell the two apart
		# and read the doctor's verdict.
		#
		# fitness_result is required (see
		# healthcare_integration.validate_patient_encounter) whenever
		# is_trial_medical_exam is set, so a trial encounter can't be
		# submitted without an actual verdict for on_submit to propagate.
		"Patient Encounter": [
			{
				"fieldname": "is_trial_medical_exam",
				"label": "Trial Medical Exam",
				"fieldtype": "Check",
				"insert_after": "appointment_type",
				"reqd": 0,
				"hidden": 0,
				"description": "This encounter is a trial candidate's medical screening - requires a Fitness Result before it can be submitted.",
			},
			{
				"fieldname": "trialist",
				"label": "Trialist",
				"fieldtype": "Link",
				"options": "Trialist",
				"insert_after": "is_trial_medical_exam",
				"reqd": 0,
				"hidden": 0,
				"description": "Only set for a re-trial of an existing Trialist. Leave blank for a first-time trial candidate - see the linked Patient's own Trial Candidacy fields instead.",
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


def make_client_scripts():
	"""Adds a "Register as Trial Candidate" button to the Patient form
	via a Client Script, instead of editing anything inside the
	Healthcare app itself (same non-invasive approach as the doc_events
	hooks in healthcare_integration.py). Idempotent - safe to call on
	every after_install/after_migrate.
	"""
	_upsert_client_script(
		name="Sports Complex: Patient Trial Candidate Button",
		dt="Patient",
		view="Form",
		script=_PATIENT_TRIAL_CANDIDATE_SCRIPT,
	)


def _upsert_client_script(name, dt, view, script):
	if frappe.db.exists("Client Script", name):
		doc = frappe.get_doc("Client Script", name)
	else:
		doc = frappe.new_doc("Client Script")
		doc.name = name

	doc.dt = dt
	doc.view = view
	doc.script = script
	doc.enabled = 1
	doc.flags.ignore_permissions = True
	doc.save(ignore_permissions=True)


# Kept as a plain string (not a .js asset) since Client Script content is
# stored/executed straight out of the database, not bundled - see
# make_client_scripts() above.
_PATIENT_TRIAL_CANDIDATE_SCRIPT = """
frappe.ui.form.on("Patient", {
	refresh: function(frm) {
		if (frm.doc.__islocal) {
			return;
		}

		if (frm.doc.sc_trialist) {
			frm.add_custom_button(__("View Trialist Record"), function() {
				frappe.set_route("Form", "Trialist", frm.doc.sc_trialist);
			});
			return;
		}

		if (frm.doc.sc_trial_clearance_status === "Pending") {
			frm.dashboard.add_indicator(__("Trial medical exam awaiting doctor's result"), "orange");
			return;
		}

		if (frm.doc.sc_trial_clearance_status === "Cleared") {
			frm.dashboard.add_indicator(__("Medically cleared for trials - ready for sports registration"), "green");
			return;
		}

		// Not yet a candidate, or a previous attempt came back "Not Cleared"
		// (re-registering is allowed - a fresh trial medical exam is opened).
		frm.add_custom_button(__("Register as Trial Candidate"), function() {
			frappe.call({
				method: "sports_complex.sports_complex.healthcare_integration.register_trial_candidate",
				args: { patient: frm.doc.name },
				freeze: true,
				freeze_message: __("Opening trial medical exam..."),
				callback: function(r) {
					if (r.message && r.message.status === "Success") {
						frappe.show_alert({
							message: __("Registered as trial candidate - medical encounter {0} created, awaiting the doctor", [r.message.encounter]),
							indicator: "blue"
						}, 8);
						frm.reload_doc();
					}
				}
			});
		}).addClass("btn-primary");

		if (frm.doc.sc_trial_clearance_status === "Not Cleared") {
			frm.dashboard.add_indicator(__("Previous trial medical result: Not Cleared"), "red");
		}
	}
});
"""
