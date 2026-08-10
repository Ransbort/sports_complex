// Copyright (c) 2026, Pep Sports Limited and contributors
// For license information, please see license.txt

frappe.ui.form.on("Player", {
	refresh: function (frm) {
		if (frm.doc.__islocal) {
			return;
		}

		frm.add_custom_button(__("Progress Note"), function () {
			frappe.new_doc("Player Progress Note", { player: frm.doc.name });
		}, __("Create"));

		frm.add_custom_button(__("View Progress Notes"), function () {
			frappe.set_route("List", "Player Progress Note", { player: frm.doc.name });
		});

		// "A timetable should be included on the player/sports side" —
		// rather than duplicating schedule data per player, this opens
		// the shared Team Timetable filtered to the player's own team,
		// since the timetable is inherently a team-level schedule, not
		// something that varies per player within a team.
		if (frm.doc.team) {
			frm.add_custom_button(__("Team Timetable"), function () {
				frappe.set_route("List", "Team Timetable", { team: frm.doc.team });
			});
		}

		if (frm.doc.trialist) {
			frm.add_custom_button(__("View Trialist Record"), function () {
				frappe.set_route("Form", "Trialist", frm.doc.trialist);
			});
		}

		if (frm.doc.open_issues_count) {
			frm.dashboard.add_indicator(
				__("{0} open progress issue(s)", [frm.doc.open_issues_count]),
				"orange"
			);
		}
	},
});
