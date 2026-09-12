import json

import frappe
from frappe import _
from frappe.utils import nowdate, today


DEFAULT_TRIAL_APPOINTMENT_TYPE = "Trialist"


def get_trial_appointment_type():

	settings = frappe.get_cached_doc("Sports Complex Setup")
	return settings.get("trial_appointment_type") or DEFAULT_TRIAL_APPOINTMENT_TYPE


def ensure_trial_appointment_type():

	appointment_type = get_trial_appointment_type()
	if not frappe.db.exists("Appointment Type", appointment_type):
		frappe.get_doc({
			"doctype": "Appointment Type",
			"appointment_type": appointment_type,
		}).insert(ignore_permissions=True)


@frappe.whitelist()
def get_trial_appointment_type_for_client():

	return get_trial_appointment_type()

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
	# This comment is load-bearing: ensure_fitness_result_visibility_
	# script() below (and remove_fitness_result_visibility_script() in
	# uninstall.py) both find this Client Script again on a later run by
	# searching for this exact marker inside the saved script text - the
	# marker was previously declared as a local variable in both of
	# those functions but never actually written into the script body,
	# so that lookup always returned nothing. That meant every single
	# `bench migrate` after the first tried to re-insert a Client Script
	# with the same fixed name and failed with a duplicate-key
	# IntegrityError, and uninstall's own cleanup silently never found
	# anything to delete either.
	"""/* __sports_complex_fitness_result_visibility__ */
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

	marker = "__sports_complex_fitness_result_visibility__"
	fixed_name = "Sports Complex Fitness Result Visibility"
	existing_name = frappe.db.get_value(
		"Client Script",
		{"dt": "Patient Encounter", "view": "Form", "script": ("like", f"%{marker}%")},
	)
	if not existing_name and frappe.db.exists("Client Script", fixed_name):
		# Covers a site whose record predates this marker being embedded
		# in FITNESS_RESULT_VISIBILITY_SCRIPT below (see that comment) -
		# without this fallback, every migrate would keep missing the
		# marker search above and re-attempt an insert() under the same
		# fixed name, failing with a duplicate-key IntegrityError forever.
		# Falling through to the update branch here rewrites the saved
		# script to the current (marker-including) version, so the next
		# migrate finds it via the marker search as intended.
		existing_name = fixed_name
	if existing_name:
		doc = frappe.get_doc("Client Script", existing_name)
		doc.script = FITNESS_RESULT_VISIBILITY_SCRIPT
		doc.enabled = 1
		doc.save(ignore_permissions=True)
	else:
		frappe.get_doc({
			"doctype": "Client Script",
			"name": fixed_name,
			"dt": "Patient Encounter",
			"view": "Form",
			"enabled": 1,
			"script": FITNESS_RESULT_VISIBILITY_SCRIPT,
		}).insert(ignore_permissions=True)


VIEW_LAB_RESULTS_SCRIPT = (
	# Same load-bearing marker comment as FITNESS_RESULT_VISIBILITY_SCRIPT
	# above - ensure_view_lab_results_script() below finds this Client
	# Script again by searching for this exact marker inside the saved
	# script text. It was previously declared as a local variable in that
	# function but never actually written into the script body, so the
	# lookup always came up empty and every migrate after the first tried
	# to re-insert a Client Script under the same fixed name, failing
	# with a duplicate-key IntegrityError.
	"""/* __sports_complex_view_lab_results__ */
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
	fixed_name = "Sports Complex View Lab Results"
	existing_name = frappe.db.get_value(
		"Client Script",
		{"dt": "Patient Encounter", "view": "Form", "script": ("like", f"%{marker}%")},
	)
	if not existing_name and frappe.db.exists("Client Script", fixed_name):
		# Same fallback as ensure_fitness_result_visibility_script() -
		# covers a record saved before the marker was actually embedded
		# in VIEW_LAB_RESULTS_SCRIPT above, which the marker search
		# would otherwise never find, forever re-attempting an insert()
		# under this same fixed name.
		existing_name = fixed_name
	if existing_name:
		doc = frappe.get_doc("Client Script", existing_name)
		doc.script = VIEW_LAB_RESULTS_SCRIPT
		doc.enabled = 1
		doc.save(ignore_permissions=True)
	else:
		frappe.get_doc({
			"doctype": "Client Script",
			"name": fixed_name,
			"dt": "Patient Encounter",
			"view": "Form",
			"enabled": 1,
			"script": VIEW_LAB_RESULTS_SCRIPT,
		}).insert(ignore_permissions=True)


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
		return

	options_list = base_options.split("\n")
	if WITH_LAB_STATUS in options_list:
		return

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


@frappe.whitelist()
def get_encounter_lab_test_names(encounter):
	"""Every Lab Test linked to this Patient Encounter, from the two
	sources that don't share a common field (see the removed
	attach_trial_lab_results_to_encounter() comment above for why they're
	kept separate rather than merged onto the Encounter itself):

	  - doctor-ordered labs accepted through Lab Portal's
		accept_lab_request(), which write the linked Lab Test's name onto
		lab_test_prescription's custom_lab_test field. This is the path
		that serves EVERY patient encounter, sports-complex trial or
		otherwise - it's the ordinary Healthcare flow, untouched here.
	  - a trial appointment's predetermined panel, found via Lab Test's
		own sc_trial_appointment field (set at creation - see
		create_trial_lab_panel()), matched against this encounter's
		`appointment` - not reachable from the encounter's child tables at
		all, since Lab Test has no field pointing back to Patient
		Encounter, only to the Patient Appointment it was created against.
		This second source only ever contributes rows for a sports-complex
		trial appointment; guarded with has_field() below so it degrades
		to a no-op (rather than throwing) on any site/version where the
		sc_trial_appointment custom field doesn't exist - e.g. if this
		function is ever relocated out of the sports_complex app into a
		general healthcare customization, or the app is temporarily
		disabled.

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

	if appointment and frappe.get_meta("Lab Test").has_field("sc_trial_appointment"):
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