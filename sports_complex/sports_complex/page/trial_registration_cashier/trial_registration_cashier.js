// Copyright (c) 2026, Sports Complex and contributors
// For license information, please see license.txt
//
// RETIRED - collapsed into the unified Cashier page (sports_complex/
// sports_complex/page/cashier/cashier.js), which now has its own "Trial
// Registrations" tab covering exactly what this page used to do on its
// own (see cashier.py's get_trial_billing_queue()/
// create_trial_payment_entry(), ported here unchanged). This file is kept
// only as a redirect stub - not deleted outright - so an old bookmark,
// sidebar shortcut, or desk search hit for "Trial Registration Cashier"
// still lands somewhere useful instead of a broken/missing-controller
// page. The full board implementation this file used to contain now
// lives in cashier.js instead.

frappe.pages['trial-registration-cashier'].on_page_load = function (wrapper) {
	frappe.ui.make_app_page({
		parent: wrapper,
		title: __('Trial Registration Cashier'),
		single_column: true,
	});

	frappe.show_alert({
		message: __('Trial Registration Cashier has moved into the unified Cashier page.'),
		indicator: 'blue',
	}, 5);
	frappe.set_route('cashier');
};
