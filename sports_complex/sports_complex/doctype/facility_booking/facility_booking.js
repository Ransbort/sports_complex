// Copyright (c) 2026, Your Company and contributors
// For license information, please see license.txt

frappe.ui.form.on("Facility Booking", {
	refresh(frm) {
		// Show a quick link to the linked Sales Invoice once one exists
		if (frm.doc.sales_invoice) {
			frm.add_custom_button(__("View Sales Invoice"), () => {
				frappe.set_route("Form", "Sales Invoice", frm.doc.sales_invoice);
			});
		}

		// Colour the booking status indicator
		const status_colors = {
			Draft: "grey",
			Confirmed: "blue",
			"Checked-In": "orange",
			Completed: "green",
			Cancelled: "red",
			"No-show": "red",
		};
		if (frm.doc.booking_status) {
			frm.page.set_indicator(
				frm.doc.booking_status,
				status_colors[frm.doc.booking_status] || "grey"
			);
		}
	},

	booking_date(frm) {
		frm.trigger("filter_court_by_maintenance");
	},

	court(frm) {
		frm.trigger("filter_court_by_maintenance");
	},

	filter_court_by_maintenance(frm) {
		// Only show courts belonging to an active Sports Facility;
		// double-booking / maintenance overlap is still enforced server-side.
		frm.set_query("court", () => {
			return {
				filters: {
					is_active: 1,
				},
			};
		});
	},
});

// ---------------------------------------------------------------------
// Calendar View config
// Facility Booking stores date and time as separate fields
// (booking_date, start_time, end_time) rather than combined datetimes,
// so the default calendar field_map (which expects "start"/"end"
// datetime fields directly on the doc) doesn't work. get_events_method
// below combines them server-side.
// ---------------------------------------------------------------------
frappe.views.calendar["Facility Booking"] = {
	field_map: {
		id: "name",
		title: "title",
		start: "start",
		end: "end",
		allDay: "all_day",
		status: "status",
	},
	get_events_method:
		"sports_complex.sports_complex.doctype.facility_booking.facility_booking.get_booking_events",
	filters: [
		{
			fieldtype: "Link",
			fieldname: "court",
			options: "Court",
			label: __("Court"),
		},
		{
			fieldtype: "Select",
			fieldname: "booking_status",
			options: "Draft\nConfirmed\nChecked-In\nCompleted\nCancelled\nNo-show",
			label: __("Status"),
		},
	],
	get_css_class: function (data) {
		if (data.status === "Cancelled" || data.status === "No-show") return "danger";
		if (data.status === "Completed") return "success";
		if (data.status === "Confirmed") return "warning";
		return "default";
	},
};