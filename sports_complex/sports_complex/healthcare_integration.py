# Copyright (c) 2026, Pep Sports Limited and contributors
# For license information, please see license.txt

"""Hooks into the Healthcare app's Patient Appointment / Patient Encounter
doctypes, wired up via this app's hooks.py. Keeps the trial-candidacy
pipeline in sync with the doctor's verdict.

This module still owns every bit of trial-specific decision-making, but as
of the predetermined-lab stage below, Front Desk itself
(healthcare/page/front_desk/front_desk.py and front_desk.js) is no longer
completely untouched — it has three small, generic extension points added
to it (a "lab" tab alongside checkin/queue/nurse/doctor, a
tab_for_status entry, and a _route_after_vitals() hook called from
save_vitals()). None of those three contain trial-specific logic
themselves; they only ever call into this module. See
route_trial_after_vitals() below for exactly where control crosses back
over.

Registration flow (medical-first, per the team's confirmed redesign):
  1. A person enters the pipeline the moment ANY Patient Appointment gets
     created for them with Appointment Type = the site's configured Trial
     Appointment Type (Sports Complex Setup > Trials, defaults to
     "Trialist" — see get_trial_appointment_type() below) — a walk-in
     check-in or a pre-booked appointment, first exam or a re-trial, it's
     all the exact same mechanism now. Front Desk's own check-in flow
     (checkin/queue/nurse/lab/doctor tabs) is used as-is; nothing sports-
     specific needs to exist there. on_patient_appointment_after_insert()
     below reacts to that and flags the Patient as a trial candidate.
  2. The person goes through Front Desk's normal queue - Nurse Station
     takes vitals. For a trial appointment, save_vitals() no longer sends
     them straight to the doctor: route_trial_after_vitals() below
     intercepts (via front_desk.py's _route_after_vitals() extension
     point), auto-creates one Lab Test per row configured under Sports
     Complex Setup > Trials > Required Lab Tests (create_trial_lab_panel()
     below - already paid for by the same consultation fee charged at
     check-in, never billed a second time), and parks the appointment on
     a new "With Lab" queue_status / Lab tab instead of "With Doctor".
     Lab staff work those tests exactly like any other Lab Test, then a
     lab tech (or, for an incomplete panel, a front-desk/nursing override
     — see send_trial_to_doctor() below) sends the appointment on to the
     Doctor Queue. Only then does the doctor call start_consultation(),
     which creates the actual Patient Encounter, inherits appointment_type
     from the appointment automatically, and — via
     attach_trial_lab_results_to_encounter() below, hooked on the
     Encounter's own before_insert — arrives pre-populated with the
     completed lab results in its normal Lab Tests section, nothing for
     the doctor to go hunting for. The doctor records a Fitness Result
     and submits. If Sports Complex Setup's Required Lab Tests table is
     left empty, route_trial_after_vitals() declines to claim the
     appointment and it goes straight to the doctor as before - the lab
     stage is opt-in per site, not a hard requirement of the trial flow.
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
  Lab Test:
    - sc_trial_appointment      Link -> Patient Appointment (auto-set only
                                 on the Lab Tests create_trial_lab_panel()
                                 itself creates - see that function)

Plus, on the Healthcare app's own Healthcare Settings single (added by
healthcare/setup.py, not this app, since it's Front Desk tab-access
plumbing rather than anything trial-specific):
  - front_desk_lab_roles           Small Text, default "Laboratory User"
  - front_desk_lab_override_roles  Small Text, default "Nursing User,Physician"

...plus the "trial_appointment_type" and "trial_required_lab_tests" fields
on the Sports Complex Setup single doctype (Trials tab), and four things
auto-provisioned by install.py's after_install/after_migrate so nobody has
to create them by hand first:
  - the Appointment Type record itself, via ensure_trial_appointment_type()
  - a Client Script on Patient Encounter's Form view, via
    ensure_fitness_result_visibility_script(), that hides the whole
    "Trial Medical Exam" tab (sc_trial_tab, Fitness Result, Fitness
    Assessment Notes, and the five Medical Information fields above —
    TRIAL_ONLY_ENCOUNTER_FIELDS) entirely unless the open encounter's
    Appointment Type matches
    get_trial_appointment_type() — doctors doing an ordinary (non-trial)
    consultation never see a tab that means nothing to them.
  - a Property Setter on Patient Appointment.queue_status, via
    ensure_queue_status_with_lab_option(), that appends "With Lab" to the
    Select options Healthcare's own setup.py defines for that field —
    layered on top rather than editing that field's own definition, so
    it survives Healthcare's own after_migrate re-syncing its Custom
    Field record.
"""

import json

import frappe
from frappe import _
from frappe.utils import nowdate, today

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


# =============================================================================
# LAB STAGE — predetermined labs between vitals and the doctor
#
# For a trial appointment, save_vitals() (front_desk.py) no longer sends the
# patient straight to the doctor. route_trial_after_vitals() below is what
# front_desk.py's _route_after_vitals() extension point calls; everything
# from queue_status through the Lab tab's data and the eventual handoff back
# to the doctor lives here, not in front_desk.py/js.
# =============================================================================

WITH_LAB_STATUS = "With Lab"


def ensure_queue_status_with_lab_option():
	"""Idempotently layer a Property Setter on top of Patient Appointment.
	queue_status so WITH_LAB_STATUS is a valid option, without editing the
	Custom Field Healthcare's own setup.py owns. A Property Setter is used
	specifically because it's *not* touched when Healthcare's own
	after_migrate re-runs create_custom_fields(update=True) on that same
	Custom Field — editing the Custom Field's `options` directly here
	would just get silently reverted on the next bench migrate.

	Always recomputed from the Custom Field's own base options (not
	whatever the field currently resolves to, which could already include
	a previous run's Property Setter) so this is safe to call repeatedly
	and never doubles up "With Lab" in the list.
	"""
	base_options = frappe.db.get_value(
		"Custom Field", {"dt": "Patient Appointment", "fieldname": "queue_status"}, "options"
	)
	if not base_options:
		# Healthcare's own setup.py hasn't run yet on this site (fresh
		# install ordering) - nothing to layer on top of yet. Healthcare's
		# after_install/after_migrate always runs make_custom_fields()
		# too, so a later bench migrate picks this back up.
		return

	options_list = base_options.split("\n")
	if WITH_LAB_STATUS in options_list:
		return

	# Slot it in right after "With Nurse" so the list still reads as one
	# coherent, ordered pipeline wherever it's shown as a plain Select
	# (list filters, reports) - not load-bearing for the code itself,
	# which only ever compares queue_status by exact string.
	if "With Nurse" in options_list:
		insert_at = options_list.index("With Nurse") + 1
		options_list.insert(insert_at, WITH_LAB_STATUS)
	else:
		options_list.append(WITH_LAB_STATUS)

	from frappe.custom.doctype.property_setter.property_setter import make_property_setter

	make_property_setter(
		"Patient Appointment",
		"queue_status",
		"options",
		"\n".join(options_list),
		"Text",
	)


def _trial_lab_panel_templates():
	"""Lab Test Template names configured under Sports Complex Setup >
	Trials > Required Lab Tests, in row order. Empty list means the lab
	stage is switched off for this site - route_trial_after_vitals()
	treats that as "nothing to gate on", not an error.
	"""
	settings = frappe.get_cached_doc("Sports Complex Setup")
	return [
		row.lab_test_template
		for row in settings.get("trial_required_lab_tests") or []
		if row.lab_test_template
	]


def create_trial_lab_panel(appointment):
	"""Auto-create one Lab Test per row in the configured trial panel,
	directly against the Patient - no Patient Encounter exists yet at
	this point (same reason Vital Signs links via `appointment` rather
	than `encounter` in front_desk.py's save_vitals()).

	custom_invoice is pointed at the SAME Sales Invoice that already paid
	for this appointment's consultation fee at check-in
	(consultation_invoice) rather than creating a fresh invoice per test
	the way lab_portal.create_lab_request()/accept_*_lab_request() do for
	an ordinary lab request - the trial's one check-in payment is meant to
	cover vitals + this panel + the doctor visit as a single bundled fee
	(see Sports Complex Setup > Trials > Required Lab Tests' description),
	so nothing here should ever raise a second bill. Setting custom_invoice
	is also what puts these straight into Lab Portal's existing "Pending
	Labs" tab (custom_invoice IS NOT NULL AND status != 'Completed') with
	zero changes needed to lab_portal.py - there's no "accept" step to
	invoice, since it's already covered.

	Idempotent: skips any template that already has a Lab Test for this
	appointment, so a retried/duplicated call (e.g. save_vitals() somehow
	invoked twice) never creates a second panel.
	"""
	templates = _trial_lab_panel_templates()
	if not templates:
		return []

	appt = frappe.db.get_value(
		"Patient Appointment", appointment, ["patient", "consultation_invoice"], as_dict=True
	)
	if not appt or not appt.patient:
		return []

	patient = frappe.get_cached_doc("Patient", appt.patient)

	existing = {
		row.template
		for row in frappe.get_all(
			"Lab Test", filters={"sc_trial_appointment": appointment}, fields=["template"]
		)
	}

	created = []
	for template in templates:
		if template in existing:
			continue
		lab_test = frappe.get_doc(
			{
				"doctype": "Lab Test",
				"patient": patient.name,
				"patient_name": patient.patient_name,
				"patient_sex": patient.sex,
				"template": template,
				"status": "Draft",
				"sc_trial_appointment": appointment,
				"custom_invoice": appt.consultation_invoice,
			}
		)
		lab_test.insert(ignore_permissions=True)
		created.append(lab_test.name)

	return created


def route_trial_after_vitals(appointment, appointment_type):
	"""Called from front_desk.py's _route_after_vitals() extension point,
	right after save_vitals() submits the Vital Signs doc. Returns True if
	this appointment was claimed and fully routed here (queue_status +
	notification both handled) - False tells front_desk.py to run its own
	default "straight to the doctor" path instead.

	Two cases return False, both deliberately: a non-trial appointment
	(nothing to do with this module), and a trial appointment whose site
	has never configured any Required Lab Tests (Sports Complex Setup >
	Trials) - the lab stage is opt-in per site, not a hard requirement of
	the trial flow, so an unconfigured panel behaves exactly like the
	pre-lab-stage flow always did.
	"""
	if appointment_type != get_trial_appointment_type():
		return False

	created = create_trial_lab_panel(appointment)
	if not created:
		return False

	frappe.db.set_value("Patient Appointment", appointment, "queue_status", WITH_LAB_STATUS)

	patient_name = frappe.db.get_value("Patient Appointment", appointment, "patient_name")
	frappe.publish_realtime(
		event="queue_update",
		message={
			"department": "laboratory",
			"message": f"{patient_name} ready for trial labs ({len(created)} test(s))",
			"appointment": appointment,
		},
	)
	return True


def _configured_roles(fieldname, default_roles=None):
	configured = frappe.db.get_single_value("Healthcare Settings", fieldname)
	roles = {r.strip() for r in (configured or "").split(",") if r.strip()}
	return roles or (set(default_roles) if default_roles else set())


def user_can_access_lab_tab(user=None):
	"""Mirrors front_desk.py's own _user_can_access_tab() (deliberately
	re-implemented rather than imported - that function is a private,
	underscore-prefixed helper in another app, not something to reach
	across app boundaries for). Reads the same Healthcare Settings
	front_desk_lab_roles field front_desk.py's get_front_desk_settings()
	already surfaces to the client for hide/show purposes; this is the
	server-side enforcement side of that same check.
	"""
	user = user or frappe.session.user
	if user == "Administrator" or "System Manager" in frappe.get_roles(user):
		return True
	roles = _configured_roles("front_desk_lab_roles")
	if not roles:
		return True
	return bool(roles & set(frappe.get_roles(user)))


def user_can_override_lab_gate(user=None):
	"""Whether `user` may send a trial appointment to the doctor from the
	Lab tab before every required test is Completed (front_desk_lab_
	override_roles in Healthcare Settings - see send_trial_to_doctor()).
	"""
	user = user or frappe.session.user
	if user == "Administrator" or "System Manager" in frappe.get_roles(user):
		return True
	roles = _configured_roles("front_desk_lab_override_roles")
	if not roles:
		return False
	return bool(roles & set(frappe.get_roles(user)))


def _trial_lab_test_rows(appointment):
	return frappe.get_all(
		"Lab Test",
		filters={"sc_trial_appointment": appointment},
		fields=["name", "template", "status"],
		order_by="creation asc",
	)


@frappe.whitelist()
def get_trial_lab_queue(date=None):
	"""Feeds the Lab tab: every trial appointment currently sitting at
	WITH_LAB_STATUS for `date` (default today), each with its panel's
	per-test status so the front-end can show progress and enable/disable
	the Send to Doctor action without a second round-trip per row.
	"""
	if not user_can_access_lab_tab():
		frappe.throw(_("You are not permitted to access the Lab area of Front Desk."), frappe.PermissionError)

	date = date or nowdate()
	rows = frappe.get_all(
		"Patient Appointment",
		filters={"appointment_date": date, "queue_status": WITH_LAB_STATUS},
		fields=["name", "patient", "patient_name", "practitioner", "practitioner_name", "appointment_time"],
		order_by="appointment_time asc",
	)
	for row in rows:
		row["encounter_time"] = row.pop("appointment_time")
		tests = _trial_lab_test_rows(row["name"])
		row["tests"] = tests
		row["tests_total"] = len(tests)
		row["tests_completed"] = sum(1 for t in tests if t.status == "Completed")
		row["ready_for_doctor"] = bool(tests) and row["tests_completed"] == row["tests_total"]
	return rows


@frappe.whitelist()
def send_trial_to_doctor(appointment, override_reason=None):
	"""The Lab tab's "Send to Doctor" action. Any user with Lab tab access
	may send an appointment on once every configured test is Completed.
	Sending it on early requires both front_desk_lab_override_roles
	membership AND a non-blank reason, which is recorded as a comment on
	the Patient Appointment for an audit trail.
	"""
	tests = _trial_lab_test_rows(appointment)
	incomplete = [t for t in tests if t.status != "Completed"]

	if incomplete:
		if not user_can_override_lab_gate():
			frappe.throw(
				_("{0} of {1} required lab test(s) are not yet Completed.").format(
					len(incomplete), len(tests)
				)
			)
		if not (override_reason or "").strip():
			frappe.throw(_("A reason is required to send this patient to the doctor before labs are complete."))
	elif not user_can_access_lab_tab():
		frappe.throw(_("You are not permitted to access the Lab area of Front Desk."), frappe.PermissionError)

	frappe.db.set_value("Patient Appointment", appointment, "queue_status", "With Doctor")

	if incomplete:
		frappe.get_doc("Patient Appointment", appointment).add_comment(
			"Comment",
			text=_("Sent to doctor with {0} lab test(s) still incomplete. Reason: {1}").format(
				len(incomplete), override_reason
			),
		)

	patient_name = frappe.db.get_value("Patient Appointment", appointment, "patient_name")
	frappe.publish_realtime(
		event="queue_update",
		message={
			"department": "doctor",
			"message": f"{patient_name} ready for consultation",
			"encounter": None,
		},
	)
	return {"status": "Success"}


def attach_trial_lab_results_to_encounter(doc, method=None):
	"""Hooked on Patient Encounter's before_insert (alongside
	sync_trial_medical_history_from_patient - see hooks.py), so it fires
	the moment start_consultation() (front_desk.py, unmodified) builds the
	Encounter. Populates the Encounter's own, standard Lab Tests section
	(lab_test_prescription, the same child table doctor-ordered labs use)
	with this trial's already-completed panel, so the doctor sees the
	results in the normal place - nothing new to look for, and nothing
	billed again (invoiced=1 here, since custom_invoice was already set
	to the consultation invoice back in create_trial_lab_panel()).
	"""
	if doc.appointment_type != get_trial_appointment_type() or not doc.appointment:
		return

	completed = frappe.get_all(
		"Lab Test",
		filters={"sc_trial_appointment": doc.appointment, "status": "Completed"},
		fields=["name", "template"],
		order_by="creation asc",
	)
	for lab_test in completed:
		doc.append(
			"lab_test_prescription",
			{
				"lab_test_code": lab_test.template,
				"custom_lab_test": lab_test.name,
				"invoiced": 1,
				"lab_test_created": 1,
			},
		)


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