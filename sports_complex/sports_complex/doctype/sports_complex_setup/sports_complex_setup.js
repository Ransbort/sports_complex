// Copyright (c) 2026, Ransbort and contributors
// For license information, please see license.txt

frappe.ui.form.on("Sports Complex Setup", {
	setup: function (frm) {
		// Restrict the Account picker inside each Default Accounts row to
		// accounts that actually match that row's own Company, same pattern
		// Healthcare Settings uses for its own income_account/receivable_account
		// tables (both built on the same core "Party Account" child doctype).
		frm.set_query("account", "receivable_account", function (doc, cdt, cdn) {
			var d = locals[cdt][cdn];
			return {
				filters: {
					account_type: "Receivable",
					company: d.company,
					is_group: 0,
				},
			};
		});
		frm.set_query("account", "income_account", function (doc, cdt, cdn) {
			var d = locals[cdt][cdn];
			return {
				filters: {
					root_type: "Income",
					company: d.company,
					is_group: 0,
				},
			};
		});
	},
});
