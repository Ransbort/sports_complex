# Copyright (c) 2026, Pep Sports Limited and contributors
# For license information, please see license.txt

"""Hooks into the Healthcare app's Patient Appointment / Patient Encounter
doctypes, wired up via this app's hooks.py. Keeps the trial-candidacy
pipeline in sync with the doctor's verdict.

This module still owns every bit of trial-specific decision-making, but as
of the predetermined-lab stage below, the Healthcare app itself is no
longer completely untouched — it has one small, generic extension point
added to it: a _route_after_vitals() hook, called from nurse_station.py's
save_vitals(). It doesn't contain trial-specific logic itself; it only
ever calls into this module. See route_trial_after_vitals() below for
exactly where control crosses back over.

The "lab" tab this feeds (checking on a trial's predetermined labs and
sending the patient on to the doctor) lives on Lab Portal now
(healthcare/page/lab_portal/lab_portal.py and lab_portal.js, as its "Trial
Labs" tab - previously on Front Desk, then on Doctor Station, moved once
more so trial lab work sits alongside every other lab request instead of
splitting it across two pages). Nothing in this module changed for that
move: lab_portal.js calls the same get_trial_lab_queue()/
get_trial_lab_tests()/send_trial_to_doctor() below directly, and this
module never depended on which page hosted the tab, only on the
Healthcare Settings fields (front_desk_lab_roles/
front_desk_lab_override_roles) and the "With Lab" queue_status value
itself.

Registration flow (medical-first, per the team's confirmed redesign):
  1. A person enters the pipeline the moment ANY Patient Appointment gets
     created for them with Appointment Type = the site's configured Trial
     Appointment Type (Sports Complex Setup > Trials, defaults to
     "Trialist" — see get_trial_appointment_type() below) — a walk-in
     check-in or a pre-booked appointment, first exam or a re-trial, it's
     all the exact same mechanism now. Front Desk's own check-in flow
     (checkin/queue tabs), Nurse Station, and Doctor Station (queue, lab,
     and patient search tabs) are used as-is; nothing sports-specific
     needs to exist there. on_patient_appointment_after_insert() below
     reacts to that and flags the Patient as a trial candidate.
  2. The person goes through Front Desk's normal queue - Nurse Station
     takes vitals. For a trial appointment, nurse_station.py's
     save_vitals() no longer sends them straight to the doctor:
     route_trial_after_vitals() below intercepts (via nurse_station.py's
     _route_after_vitals() extension point), auto-creates one Lab Test per
     row configured under Sports Complex Setup > Trials > Required Lab
     Tests (create_trial_lab_panel() below - already paid for by the same
     consultation fee charged at check-in, never billed a second time),
     and parks the appointment on a new "With Lab" queue_status / Doctor
     Station's Lab tab instead of "With Doctor". Lab staff work those
     tests exactly like any other Lab Test, then a lab tech (or, for an
     incomplete panel, a front-desk/nursing override — see
     send_trial_to_doctor() below) sends the appointment on to the Doctor
     Queue. Only then does the doctor call start_consultation(),
     which creates the actual Patient Encounter, inherits appointment_type
     from the appointment automatically. The completed panel is never
     copied into the Encounter's own lab_test_prescription table - that
     child table is the doctor's own request grid (see accept_lab_request()
     in lab_portal.py), not a place for technician-completed trial results
     to land - so instead the doctor sees them via the "View Lab Results"
     button (VIEW_LAB_RESULTS_SCRIPT below, calling get_encounter_lab_
     test_names()), which reads Lab Test's own sc_trial_appointment field
     directly rather than anything stored on the Encounter. The doctor
     records a Fitness Result and submits. If Sports Complex Setup's
     Required Lab Tests table is
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
healthcare/setup.py, not this app, since it's Doctor Station tab-access
plumbing rather than anything trial-specific):
  - front_desk_lab_roles           Small Text, default "Laboratory User"
  - front_desk_lab_override_roles  Small Text, default "Nursing User,Physician"
  (field names kept as-is from when this lived on Front Desk - only the
  Small Text labels on the Healthcare Settings form changed, to "Doctor
  Station Lab Tab Roles"/"...Override Roles")

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


# Same "managed programmatic Client Script" mechanism as
# FITNESS_RESULT_VISIBILITY_SCRIPT above, for an unrelated button: a
# "View Lab Results" entry on Patient Encounter's View dropdown, next to
# Healthcare's own built-in "View Vitals" (healthcare/setup.py's
# create_view_vitals_client_script() - that one does
# frappe.set_route("List", "Vital Signs", {patient, encounter}), since
# Vital Signs carries its own `encounter` field directly). Lab Test has
# no such field - the only link back to an encounter runs through either
# (a) this encounter's own lab_test_prescription child table (Lab
# Prescription.custom_lab_test, a Custom Field healthcare/setup.py
# already applies) for doctor-ordered requests accepted through Lab
# Portal's own accept_lab_request(), or (b) Lab Test's own
# sc_trial_appointment field for a trial's predetermined panel - the two
# sources don't share a field, so this button calls the whitelisted
# get_encounter_lab_test_names() below (server-side) rather than reading
# frm.doc directly, and that server method is what actually combines
# them. A trial panel's results are deliberately never copied into
# lab_test_prescription itself - see get_encounter_lab_test_names()'s own
# docstring for why. Lives here rather than in healthcare/setup.py
# alongside its Vitals sibling because sports_complex.install's
# after_install/after_migrate hooks are what's actually proven to run
# this on every bench migrate on an already-installed site -
# healthcare/setup.py's own equivalent is only wired to after_install, so
# a change added only there would need a manual one-off run to reach a
# site that installed before it existed.
VIEW_LAB_RESULTS_SCRIPT = (
	"""// __sports_complex_view_lab_results__
// Managed by sports_complex.sports_complex.healthcare_integration.
// ensure_view_lab_results_script() - re-applied on every bench migrate.
// Edit the logic below if needed, but keep the marker comment above
// intact so that function can keep finding this record.
//
// Opens a popup showing just each linked Lab Test's own result table
// (Normal/Descriptive - whichever the template uses - plus any lab_test_
// comment), tabbed by test name when there's more than one, rather than
// navigating the doctor away from the Encounter or loading each test's
// entire Form (which used to be what this did - patient/gender fields,
// Comments/Custom Result/Medical Coding/Worksheet Print sections and
// all). The data comes straight from Lab Portal's own
// get_lab_test_detail() (healthcare/page/lab_portal/lab_portal.py,
// unmodified) - the exact same whitelisted method that already feeds
// the "Open Lab Test" popup's own result grid there - rather than
// re-deriving result rows from Lab Test's child tables by hand here, so
// this can never drift from what that popup shows. A small "Open Full
// Test" link on each tab is the escape hatch to the real Lab Test form
// for anything not covered here (attachments, worksheet print, etc.).

frappe.ui.form.on("Patient Encounter", {
	refresh: function (frm) {
		frm.add_custom_button(
			__("View Lab Results"),
			function () {
				frappe.call({
					method: "sports_complex.sports_complex.healthcare_integration.get_encounter_lab_test_names",
					args: { encounter: frm.doc.name },
					callback: function (r) {
						var lab_test_names = r.message || [];

						if (!lab_test_names.length) {
							frappe.msgprint(__("No lab tests are linked to this encounter yet."));
							return;
						}

						Promise.all(
							lab_test_names.map(function (name) {
								return frappe.call({
									method: "healthcare.healthcare.page.lab_portal.lab_portal.get_lab_test_detail",
									args: { lab_test_name: name },
								});
							})
						).then(function (responses) {
							var details = responses.map(function (resp) { return resp.message; }).filter(Boolean);

							if (!details.length) {
								frappe.msgprint(__("Could not load results for the linked lab test(s)."));
								return;
							}

							function resultsTableHtml(d) {
								if (d.result_type === "normal") {
									var rows = d.items.map(function (item) {
										return "<tr><td>" + frappe.utils.escape_html(item.label || "") + "</td>" +
											"<td>" + frappe.utils.escape_html(item.result_value || "") + "</td>" +
											"<td>" + frappe.utils.escape_html(item.uom || "") + "</td>" +
											"<td>" + frappe.utils.escape_html(item.normal_range || "") + "</td></tr>";
									}).join("");
									return '<table class="table table-bordered"><thead><tr><th>' + __("Test Name") +
										"</th><th>" + __("Result Value") + "</th><th>" + __("UOM") + "</th><th>" +
										__("Normal Range") + "</th></tr></thead><tbody>" +
										(rows || '<tr><td colspan="4" class="text-muted">' + __("No results recorded yet.") + "</td></tr>") +
										"</tbody></table>";
								}
								if (d.result_type === "descriptive") {
									var drows = d.items.map(function (item) {
										return "<tr><td>" + frappe.utils.escape_html(item.label || "") + "</td>" +
											"<td>" + frappe.utils.escape_html(item.result_value || "") + "</td></tr>";
									}).join("");
									return '<table class="table table-bordered"><thead><tr><th>' + __("Particulars") +
										"</th><th>" + __("Result Value") + "</th></tr></thead><tbody>" +
										(drows || '<tr><td colspan="2" class="text-muted">' + __("No results recorded yet.") + "</td></tr>") +
										"</tbody></table>";
								}
								return '<div class="text-muted">' +
									__("This test's result layout isn't supported in this popup - use 'Open Full Test' below instead.") +
									"</div>";
							}

							var dialog = new frappe.ui.Dialog({
								title: __("Lab Results"),
								size: "large",
							});
							dialog.$wrapper.find(".modal-footer").hide();
							var $body = dialog.$wrapper.find(".modal-body");
							$body.css({ "max-height": "70vh", "overflow-y": "auto" });

							var tabsHtml = "";
							var panesHtml = "";
							details.forEach(function (d, i) {
								var label = d.lab_test_name || d.template || d.name;
								tabsHtml += '<button type="button" class="btn btn-xs ' + (i === 0 ? "btn-primary" : "btn-default") +
									' lab-result-tab-btn" data-idx="' + i + '" style="margin-right: 6px;">' +
									frappe.utils.escape_html(label) + "</button>";
								panesHtml += '<div class="lab-result-pane" data-idx="' + i + '"' + (i === 0 ? "" : ' style="display:none;"') + ">" +
									(d.lab_test_comment ? '<div class="text-muted" style="margin-bottom: 8px;"><strong>' + __("Comments") +
										":</strong> " + frappe.utils.escape_html(d.lab_test_comment) + "</div>" : "") +
									resultsTableHtml(d) +
									'<div style="margin-top: 10px;"><a href="/app/lab-test/' + encodeURIComponent(d.name) +
									'" target="_blank">' + __("Open Full Test") + "</a></div>" +
									"</div>";
							});

							$body.html(
								(details.length > 1 ? '<div style="margin-bottom: 12px;">' + tabsHtml + "</div>" : "") + panesHtml
							);

							$body.find(".lab-result-tab-btn").on("click", function () {
								var idx = $(this).data("idx");
								$body.find(".lab-result-tab-btn").removeClass("btn-primary").addClass("btn-default");
								$(this).removeClass("btn-default").addClass("btn-primary");
								$body.find(".lab-result-pane").hide();
								$body.find('.lab-result-pane[data-idx="' + idx + '"]').show();
							});

							dialog.show();
						});
					},
				});
			},
			__("View"),
		);
	},
});
"""
)


def ensure_view_lab_results_script():
	"""Idempotently create/update the Client Script that adds the "View
	Lab Results" button described above. Called from sports_complex.install
	(after_install/after_migrate) - safe to call repeatedly; matches on the
	marker comment inside the script content, same reasoning as
	ensure_fitness_result_visibility_script() above.
	"""
	marker = "__sports_complex_view_lab_results__"
	existing_name = frappe.db.get_value(
		"Client Script",
		{"dt": "Patient Encounter", "view": "Form", "script": ("like", f"%{marker}%")},
	)
	if existing_name:
		doc = frappe.get_doc("Client Script", existing_name)
		doc.script = VIEW_LAB_RESULTS_SCRIPT
		doc.enabled = 1
		doc.save(ignore_permissions=True)
	else:
		frappe.get_doc({
			"doctype": "Client Script",
			# Same reasoning as Fitness Result Visibility's own name above -
			# fixed and descriptive so re-running this after a manual
			# deletion recreates the same record name.
			"name": "Sports Complex View Lab Results",
			"dt": "Patient Encounter",
			"view": "Form",
			"enabled": 1,
			"script": VIEW_LAB_RESULTS_SCRIPT,
		}).insert(ignore_permissions=True)


# A "Labs" dashboard group used to be layered onto Patient Encounter's
# existing grouped "linked documents" cards (Orders, Inpatient, Notes/
# Tasks/Vitals, Medical Records - all baked into the vendored
# patient_encounter.json's own `links` array) via frm.dashboard.
# add_transactions(["Lab Test"]) from a Client Script. Removed: that
# front-end grouping call is only half the picture - the moment the form
# loads, the client also asks the server (frappe.desk.notifications.
# get_open_count) for a badge count for every item shown, on EVERY
# dashboard group, including ones added this way. The server resolves
# that by looking up each item doctype's link_fieldname back to Patient
# Encounter from the doctype's own metadata - and since Lab Test has no
# such field (its only link is sc_trial_appointment, pointing at Patient
# Appointment, two hops away - see get_trial_lab_tests()'s neighbourhood
# above), the server had nothing correct to resolve and fell through to
# an unrelated field name from a different group, throwing "Unknown
# column 'order_group'" on every single Patient Encounter form load - a
# real, confirmed production error, not just the imprecision this was
# originally flagged as living with. Frappe's linked-document dashboard
# framework fundamentally can't express "count rows in Lab Test whose
# sc_trial_appointment matches the Patient Appointment this Encounter
# points at" - that needs a two-table join, and the framework only ever
# filters one doctype by one fieldname equal to the parent's own name.
# The doctor still reaches a trial's completed panel exactly as
# accurately via the "View Lab Results" button above (get_encounter_lab_
# test_names()), which never goes through this badge-count subsystem.
#
# remove_lab_dashboard_group_script() below is the active teardown for a
# site that already ran the buggy version - same reasoning and pattern as
# sports_complex.install.remove_stale_trial_medical_exam_field(): merely
# no longer creating the Client Script wouldn't retroactively delete one
# a previous bench migrate already inserted.
def remove_lab_dashboard_group_script():
	"""One-time cleanup for a site that already ran the "Labs" dashboard
	group Client Script described above (removed as of this change - see
	the comment above). Deletes it by the same marker comment
	ensure_lab_dashboard_group_script() used to match on. Safe to call
	repeatedly: a no-op once it's gone.
	"""
	marker = "__sports_complex_lab_dashboard_group__"
	existing_name = frappe.db.get_value(
		"Client Script",
		{"dt": "Patient Encounter", "view": "Form", "script": ("like", f"%{marker}%")},
	)
	if existing_name:
		frappe.delete_doc("Client Script", existing_name, ignore_permissions=True, force=True)
		frappe.clear_cache(doctype="Patient Encounter")


# =============================================================================
# LAB STAGE — predetermined labs between vitals and the doctor
#
# For a trial appointment, nurse_station.py's save_vitals() no longer sends
# the patient straight to the doctor. route_trial_after_vitals() below is
# what nurse_station.py's _route_after_vitals() extension point calls;
# everything from queue_status through the Lab tab's data (now on Doctor
# Station - see doctor_station.py/js) and the eventual handoff back to the
# doctor lives here, not in nurse_station.py or doctor_station.py/js.
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
	than `encounter` in nurse_station.py's save_vitals()).

	custom_invoice is pointed at the SAME Sales Invoice that already paid
	for this appointment's consultation fee at check-in
	(consultation_invoice) rather than creating a fresh invoice per test
	the way lab_portal.create_lab_request()/accept_*_lab_request() do for
	an ordinary lab request - the trial's one check-in payment is meant to
	cover vitals + this panel + the doctor visit as a single bundled fee
	(see Sports Complex Setup > Trials > Required Lab Tests' description),
	so nothing here should ever raise a second bill. Setting custom_invoice
	is also what puts these straight into Lab Portal's existing "Pending
	Labs" tab (custom_invoice IS NOT NULL OR invoiced = 1, AND status !=
	'Completed') with zero changes needed to lab_portal.py's routing
	beyond that - there's no "accept" step to invoice, since it's already
	covered.

	When consultation_invoice is blank - the Trial Appointment Type's
	consulting charge resolved to $0/unset at check-in, so Front Desk
	never raised a consultation invoice at all (see front_desk.py's
	_finalize_checkin()) - there's nothing to point custom_invoice at.
	That used to leave these Lab Tests looking exactly like an ordinary
	un-invoiced request: they'd land in Requested Labs, and accepting one
	there would try to raise a brand new Sales Invoice for a "bundled"
	fee that was never actually charged. Since a free trial visit means
	the whole visit - including its lab panel - is free, these are marked
	invoiced=1 directly instead: nothing to bill, so nothing should ever
	be billed. lab_portal.py's get_requested_labs()/get_pending_labs()
	both key off this same invoiced flag (in addition to custom_invoice)
	for direct-sourced rows, so a free panel test routes straight to
	Pending Labs - shown there with no linked invoice, same as a bundled
	paid one, just nothing owed.

	Duplicate-safe across more than just this one appointment: skips any
	template for which the Patient already has an earlier, non-cancelled
	Lab Test from ANOTHER trial appointment's panel - i.e. this same
	panel being raised twice for the same patient (a second Trial
	Appointment, or a previous call for this same appointment). This
	originally only checked Lab Tests already linked to *this*
	appointment, which meant a patient routed through vitals more than
	once ended up with two open Lab Test records for the same template -
	one from the earlier trial visit, one freshly auto-created and marked
	Free - both sitting in Pending Labs at once.

	Deliberately scoped to trial-panel-sourced Lab Tests only
	(sc_trial_appointment is set) - an ordinary doctor-ordered Lab
	Prescription off a Patient Encounter is a separate request for a
	separate reason (the doctor's own clinical judgement on that visit)
	from the trial's own required screening panel (what a trialist needs
	for the trial examination itself). Sharing an Item Template name
	(e.g. "Typhoid") doesn't make them the same request, so neither is
	ever allowed to suppress the other. A patient whose earlier panel
	entry for that template is already Cancelled still gets a fresh one.
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

	# Any earlier, non-cancelled trial-panel Lab Test the patient already
	# has for one of these templates - i.e. an earlier Trial Appointment
	# already raised this same panel entry - counts as "already covered".
	# Scoped to sc_trial_appointment IS SET so an ordinary doctor-ordered
	# Lab Prescription (a separate request, off a Patient Encounter) is
	# never treated as covering the trial panel, or vice versa. See
	# docstring above.
	existing = {
		row.template
		for row in frappe.get_all(
			"Lab Test",
			filters={
				"patient": patient.name,
				"template": ["in", templates],
				"sc_trial_appointment": ["is", "set"],
				"status": ["!=", "Cancelled"],
				"docstatus": ["!=", 2],
			},
			fields=["template"],
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
				# See docstring above - a free (unbilled) trial visit means
				# nothing is owed for its lab panel either.
				"invoiced": 1 if not appt.consultation_invoice else 0,
			}
		)
		lab_test.insert(ignore_permissions=True)
		created.append(lab_test.name)

	return created


def route_trial_after_vitals(appointment, appointment_type):
	"""Called from nurse_station.py's _route_after_vitals() extension
	point, right after save_vitals() submits the Vital Signs doc. Returns
	True if this appointment was claimed and fully routed here
	(queue_status + notification both handled) - False tells
	nurse_station.py to run its own default "straight to the doctor" path
	instead.

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
	"""Mirrors the shape of front_desk.py's own _user_can_access_tab()/
	nurse_station.py's _user_can_access_nurse_station() (deliberately
	re-implemented rather than imported - those are private, underscore-
	prefixed helpers in another app, not something to reach across app
	boundaries for). Reads Healthcare Settings' front_desk_lab_roles
	field directly - unlike Front Desk's own tabs, the Trial Labs tab
	(now on Lab Portal) has no client-side hide/show equivalent to
	get_front_desk_settings()'s allowed_tabs; this is the only gate it
	has, so it's enforced purely server-side on every call below.
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
def get_trial_lab_queue(date=None, to_date=None):
	"""Feeds the Lab tab: every trial appointment currently sitting at
	WITH_LAB_STATUS for `date` (default today) - or, when `to_date` is
	also given, for that whole date range - each with its panel's
	per-test status so the front-end can show progress and enable/disable
	the Send to Doctor action without a second round-trip per row.
	"""
	if not user_can_access_lab_tab():
		frappe.throw(_("You are not permitted to access the Lab area of Doctor Station."), frappe.PermissionError)

	date = date or nowdate()
	rows = frappe.get_all(
		"Patient Appointment",
		filters={
			"appointment_date": ["between", [date, to_date]] if to_date else date,
			"queue_status": WITH_LAB_STATUS,
		},
		fields=[
			"name",
			"patient",
			"patient_name",
			"practitioner",
			"practitioner_name",
			"appointment_date",
			"appointment_time",
		],
		order_by="appointment_date asc, appointment_time asc",
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
def get_trial_lab_tests(date=None, to_date=None):
	"""Feeds Lab Portal's Trial Labs tab: one row per individual Lab Test
	in a trial panel, not one row per appointment like get_trial_lab_queue()
	above - Lab Portal renders every tab as one card per Lab Test, so this
	flattens the same underlying data to match that shape instead of
	grouping tests under their appointment. Appointment-level context
	(progress across the whole panel, whether it's ready to send to the
	doctor, and now which day it's on now that a range can span more than
	one) is duplicated onto every row belonging to that appointment so
	the front-end doesn't need a second round-trip per card, and
	payment_status is resolved the same way lab_portal.py's own
	get_pending_labs() resolves it for a direct-sourced row: no
	custom_invoice at all means the panel was free (see
	create_trial_lab_panel()'s docstring), otherwise it's Paid/Unpaid
	depending on the linked Sales Invoice's own status.
	"""
	appointments = get_trial_lab_queue(date=date, to_date=to_date)

	template_names = {}
	all_templates = {test["template"] for appt in appointments for test in appt["tests"]}
	if all_templates:
		template_names = {
			d.name: d.lab_test_name
			for d in frappe.get_all(
				"Lab Test Template",
				filters={"name": ["in", list(all_templates)]},
				fields=["name", "lab_test_name"],
			)
		}

	rows = []
	for appt in appointments:
		for test in appt["tests"]:
			invoice_name = frappe.db.get_value("Lab Test", test["name"], "custom_invoice")
			if invoice_name:
				invoice_status = frappe.db.get_value("Sales Invoice", invoice_name, "status")
				payment_status = "Paid" if invoice_status == "Paid" else "Unpaid"
			else:
				payment_status = "Free"

			rows.append(
				{
					"lab_test": test["name"],
					"template": test["template"],
					"lab_test_name": template_names.get(test["template"]) or test["template"],
					"lab_test_status": test["status"],
					"payment_status": payment_status,
					"appointment": appt["name"],
					"patient": appt["patient"],
					"patient_name": appt["patient_name"],
					"practitioner": appt["practitioner"],
					"practitioner_name": appt["practitioner_name"],
					"appointment_date": appt["appointment_date"],
					"encounter_time": appt["encounter_time"],
					"tests_total": appt["tests_total"],
					"tests_completed": appt["tests_completed"],
					"ready_for_doctor": appt["ready_for_doctor"],
				}
			)
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
		frappe.throw(_("You are not permitted to access the Lab area of Doctor Station."), frappe.PermissionError)

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


# attach_trial_lab_results_to_encounter() used to live here, hooked on
# Patient Encounter's before_insert, and copied a trial's completed panel
# into the Encounter's own lab_test_prescription child table so the
# doctor would see it "in the normal place". Removed: lab_test_prescription
# (Lab Prescription) is the doctor's OWN request grid - the same table
# accept_lab_request() in lab_portal.py fills in when a lab tech accepts a
# doctor-ordered request - and a technician-completed trial panel the
# doctor never requested doesn't belong in it. The doctor now sees a
# trial's completed panel exclusively via the "View Lab Results" button
# (VIEW_LAB_RESULTS_SCRIPT above), which reads Lab Test's own
# sc_trial_appointment field directly - see get_encounter_lab_test_names()
# below, which VIEW_LAB_RESULTS_SCRIPT calls. hooks.py's before_insert
# list for Patient Encounter no longer references this function. (A
# separate "Labs" dashboard card was also tried and removed - see
# remove_lab_dashboard_group_script() above for why.)


@frappe.whitelist()
def get_encounter_lab_test_names(encounter):
	"""Every Lab Test linked to this Patient Encounter, from the two
	sources that don't share a common field (see the removed
	attach_trial_lab_results_to_encounter() comment above for why they're
	kept separate rather than merged onto the Encounter itself):

	  - doctor-ordered labs accepted through Lab Portal's
		accept_lab_request(), which write the linked Lab Test's name onto
		lab_test_prescription's custom_lab_test field.
	  - a trial appointment's predetermined panel, found via Lab Test's
		own sc_trial_appointment field (set at creation - see
		create_trial_lab_panel()), matched against this encounter's
		`appointment` - not reachable from the encounter's child tables at
		all, since Lab Test has no field pointing back to Patient
		Encounter, only to the Patient Appointment it was created against.

	Called from the client (VIEW_LAB_RESULTS_SCRIPT's "View Lab Results"
	button) rather than read straight off frm.doc, specifically because
	that second source needs a server-side query the form has no data
	for. Only "Completed" trial-panel tests are included - matching what
	attach_trial_lab_results_to_encounter() used to filter on before its
	removal - an in-progress trial panel isn't a "result" yet; doctor-
	ordered rows are returned regardless of status, matching the button's
	prior behaviour for that source.
	"""
	if not frappe.has_permission("Patient Encounter", "read", encounter):
		frappe.throw(_("Not permitted to read this Patient Encounter."), frappe.PermissionError)

	appointment = frappe.db.get_value("Patient Encounter", encounter, "appointment")

	names = set(
		frappe.get_all(
			"Lab Prescription",
			filters={
				"parent": encounter,
				"parenttype": "Patient Encounter",
				"custom_lab_test": ["is", "set"],
			},
			pluck="custom_lab_test",
		)
	)

	if appointment:
		names.update(
			frappe.get_all(
				"Lab Test",
				filters={"sc_trial_appointment": appointment, "status": "Completed"},
				pluck="name",
			)
		)

	return sorted(names)


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
	doctor_station.py, not touched by this app) rather than through the form
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
	first insert() that start_consultation() in doctor_station.py does to
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