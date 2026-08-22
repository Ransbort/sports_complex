// Copyright (c) 2026, Your Company and contributors
// For license information, please see license.txt

frappe.ui.form.on("Check-In", {
	refresh(frm) {
		frm.trigger("filter_facility_booking");
	},

	filter_facility_booking(frm) {
		// check_in.py's validate() already rejects a booking that isn't
		// Confirmed - filtering the link's own search to the same set
		// means staff can't even pick an ineligible booking to begin
		// with, rather than picking one and then hitting that error.
		frm.set_query("facility_booking", () => {
			return {
				filters: {
					booking_status: "Confirmed",
				},
			};
		});
	},
});
