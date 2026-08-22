// Copyright (c) 2026, Your Company
// License: MIT

// Venue's "Location" field is a Geolocation field (an interactive
// Leaflet/OpenStreetMap widget - no Google Maps API key needed). Left on
// its own it's just a blank world map until someone manually drops a
// pin. This wires it up to auto-populate from whatever Address/City the
// admin already typed, via the server-side geocode_venue_address()
// lookup in venue.py, plus a manual "Locate on Map" button for
// re-fetching after an edit.

frappe.ui.form.on("Venue", {
	refresh(frm) {
		frm.add_custom_button(__("Locate on Map"), () => locate_on_map(frm, false));
	},
	address(frm) {
		maybe_auto_locate(frm);
	},
	city(frm) {
		maybe_auto_locate(frm);
	},
});

function maybe_auto_locate(frm) {
	// Only auto-fetch while there's no pin yet. Once a location exists -
	// whether from an earlier auto-fetch or the admin dragging the pin
	// themselves - further address edits shouldn't silently overwrite a
	// manually-corrected position. Re-locating after that is what the
	// "Locate on Map" button is for.
	if (frm.doc.location) return;
	if (!frm.doc.city && !frm.doc.address) return;
	locate_on_map(frm, true);
}

function locate_on_map(frm, silent) {
	if (!frm.doc.city && !frm.doc.address) {
		if (!silent) frappe.msgprint(__("Enter an address or city first"));
		return;
	}

	frappe.call({
		method: "sports_complex.sports_complex.doctype.venue.venue.geocode_venue_address",
		args: { address: frm.doc.address, city: frm.doc.city },
		freeze: !silent,
		freeze_message: __("Locating..."),
	}).then((r) => {
		const data = r.message;
		if (!data) return;

		const geojson = {
			type: "FeatureCollection",
			features: [
				{
					type: "Feature",
					properties: {},
					geometry: { type: "Point", coordinates: [data.lon, data.lat] },
				},
			],
		};

		frm.set_value("location", JSON.stringify(geojson));
		frm.refresh_field("location");

		if (!silent) {
			frappe.show_alert({ message: __("Found: {0}", [data.display_name]), indicator: "green" });
		}
	}).catch(() => {
		// silent (auto) lookups fail quietly - a vague city name may not
		// geocode, and that shouldn't interrupt someone still typing an
		// address. The explicit button click already surfaces the
		// server's error via frappe.call's own error dialog.
	});
}
