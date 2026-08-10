// Copyright (c) 2026, Pep Sports Limited and contributors
// For license information, please see license.txt

frappe.ui.form.on("Trialist", {
	refresh: function (frm) {
		// Only offer conversion on a saved, not-yet-converted trialist.
		// Once player is set, the "Player Conversion" section itself
		// shows the read-only link — no button needed, and re-running
		// this would create a second Player against the same trialist.
		if (!frm.doc.__islocal && !frm.doc.player) {
			frm.add_custom_button(__("Mark as Player"), function () {
				show_player_conversion_dialog(frm);
			}).addClass("btn-primary");
		}

		if (frm.doc.player) {
			frm.add_custom_button(__("View Player"), function () {
				frappe.set_route("Form", "Player", frm.doc.player);
			});
		}
	},
});

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
