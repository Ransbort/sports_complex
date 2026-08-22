// Copyright (c) 2026, Your Company and contributors
// For license information, please see license.txt

frappe.ui.form.on("Check-Out", {
	refresh(frm) {
		frm.trigger("filter_facility_booking");
	},

	filter_facility_booking(frm) {
		// Same idea as Check-In's own filter_facility_booking (see
		// check_in.js): check_out.py's validate() only accepts a booking
		// that's currently Checked-In, so the link's search is narrowed to
		// the same set rather than letting staff pick an ineligible
		// booking and only find out from a server-side error.
		frm.set_query("facility_booking", () => {
			return {
				filters: {
					booking_status: "Checked-In",
				},
			};
		});
	},
});
