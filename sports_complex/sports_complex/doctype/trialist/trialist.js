// Copyright (c) 2026, Pep Sports Limited and contributors
// For license information, please see license.txt

frappe.ui.form.on("Trialist", {
	setup: function (frm) {
		// Medical-first flow: only surface Patients who are already
		// cleared for trials and not yet registered as a Trialist - see
		// trial_candidate_patient_query() in trialist.py.
		frm.set_query("patient", function () {
			return {
				query: "sports_complex.sports_complex.doctype.trialist.trialist.trial_candidate_patient_query",
			};
		});
	},

	patient: function (frm) {
		// Pulls across everything medical/front-desk already captured
		// for this cleared Patient, so sports staff only have to type
		// the sport-specific fields (dominant foot, playing level,
		// previous club, interests, experience, trial batch, etc.) -
		// see get_patient_snapshot() in trialist.py.
		if (!frm.doc.patient) {
			return;
		}

		frappe.call({
			method: "sports_complex.sports_complex.doctype.trialist.trialist.get_patient_snapshot",
			args: { patient: frm.doc.patient },
			freeze: true,
			freeze_message: __("Loading patient details..."),
			callback: function (r) {
				if (!r.message) {
					return;
				}
				const snapshot = r.message;
				Object.keys(snapshot).forEach(function (fieldname) {
					if (snapshot[fieldname] !== null && snapshot[fieldname] !== undefined) {
						frm.set_value(fieldname, snapshot[fieldname]);
					}
				});
				frappe.show_alert({
					message: __("Patient details loaded - fill in the sport-specific sections below."),
					indicator: "green",
				}, 6);
			},
			error: function () {
				// get_patient_snapshot() throws (e.g. not cleared yet, or
				// already converted) - clear the pick so the form doesn't
				// end up half-populated against an invalid patient.
				frm.set_value("patient", "");
			},
		});
	},

	refresh: function (frm) {
		if (frm.doc.__islocal || frm.doc.player) {
			// Nothing to do pre-save, and a converted trialist is done —
			// see the "View Player" button below instead.
		} else if (frm.doc.medical_clearance_status === "Cleared") {
			// Cleared — sport-specific sections are unlocked (see
			// depends_on in trialist.json) and conversion is allowed.
			frm.add_custom_button(__("Mark as Player"), function () {
				show_player_conversion_dialog(frm);
			}).addClass("btn-primary");
		} else if (frm.doc.medical_clearance_status === "Pending") {
			// Already sent — nothing to click, just make the wait state
			// visible instead of silently showing no button at all.
			frm.dashboard.add_indicator(
				__("Awaiting doctor's medical clearance"),
				"orange"
			);
		} else {
			// Not sent yet ("" or "Not Cleared" — Not Cleared allows
			// re-sending, e.g. after injury recovery).
			frm.add_custom_button(__("Send to Clinic"), function () {
				send_to_clinic(frm);
			}).addClass("btn-primary");

			if (frm.doc.medical_clearance_status === "Not Cleared") {
				frm.dashboard.add_indicator(
					__("Previous medical result: Not Cleared"),
					"red"
				);
			}
		}

		if (frm.doc.medical_encounter) {
			frm.add_custom_button(__("View Medical Encounter"), function () {
				frappe.set_route("Form", "Patient Encounter", frm.doc.medical_encounter);
			});
		}

		if (frm.doc.player) {
			frm.add_custom_button(__("View Player"), function () {
				frappe.set_route("Form", "Player", frm.doc.player);
			});
		}
	},
});

function send_to_clinic(frm) {
	frappe.call({
		method: "sports_complex.sports_complex.doctype.trialist.trialist.send_to_clinic",
		args: { trialist: frm.doc.name },
		freeze: true,
		freeze_message: __("Sending to clinic..."),
		callback: function (r) {
			if (r.message && r.message.status === "Success") {
				frappe.show_alert({
					message: __("Sent to clinic — medical encounter {0} created, awaiting the doctor", [r.message.encounter]),
					indicator: "blue",
				}, 8);

				// Deliberately no navigation - the clinic finds this
				// encounter in their own Patient Encounter worklist;
				// there's no reason to route a sports-complex user
				// through it.
				frm.reload_doc();
			}
		},
	});
}

function show_player_conversion_dialog(frm) {
	// Only the fields that genuinely aren't already on the trialist's
	// registration data — everything else transfers automatically on
	// the backend (see convert_trialist_to_player in trialist.py).
	const dialog = new frappe.ui.Dialog({
		title: __("Register {0} as Player", [frm.doc.full_name]),
		fields: [
			{
				fieldtype: "Link",
				fieldname: "team",
				label: __("Team"),
				options: "Team",
				default: frm.doc.preferred_team,
				description: __("Defaults to the trial group — change if final squad placement differs"),
			},
			{
				fieldtype: "Int",
				fieldname: "jersey_number",
				label: __("Jersey Number"),
			},
			{
				fieldtype: "Select",
				fieldname: "player_category",
				label: __("Player Category"),
				options: "\nFirst Team\nReserve\nAcademy\nYouth",
			},
			{
				fieldtype: "Date",
				fieldname: "joining_date",
				label: __("Joining Date"),
				default: frappe.datetime.get_today(),
			},
		],
		primary_action_label: __("Register as Player"),
		primary_action: function (values) {
			frappe.call({
				method: "sports_complex.sports_complex.doctype.trialist.trialist.convert_trialist_to_player",
				args: {
					trialist: frm.doc.name,
					team: values.team,
					jersey_number: values.jersey_number,
					player_category: values.player_category,
					joining_date: values.joining_date,
				},
				freeze: true,
				freeze_message: __("Registering as Player..."),
				callback: function (r) {
					if (r.message && r.message.status === "Success") {
						dialog.hide();
						frappe.show_alert({
							message: __("{0} registered as Player {1}", [frm.doc.full_name, r.message.player]),
							indicator: "green",
						}, 6);
						frappe.set_route("Form", "Player", r.message.player);
					}
				},
			});
		},
	});

	dialog.show();
}
