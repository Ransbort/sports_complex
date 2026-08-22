# Copyright (c) 2026, Your Company
# License: MIT

import frappe
import requests
from frappe import _
from frappe.model.document import Document

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"


class Venue(Document):
	def validate(self):
		if self.operating_hours_from and self.operating_hours_to:
			if self.operating_hours_from >= self.operating_hours_to:
				frappe.throw("Operating Hours From must be earlier than Operating Hours To")


@frappe.whitelist()
def geocode_venue_address(address=None, city=None):
	"""Look up (lat, lon) for a venue's Address/City via OpenStreetMap's
	free Nominatim geocoder - no API key or billing account needed,
	unlike Google Maps. Called from venue.js so the Location
	(Geolocation) field's map can be populated straight from whatever
	address text the admin already typed, instead of leaving them to
	manually drop a pin on a blank world map.

	Deliberately server-side rather than a client-side fetch to
	Nominatim: their usage policy requires a real, identifying
	User-Agent and caps usage at ~1 request/second, which is easier to
	guarantee from one trusted place than from arbitrary browsers, and
	avoids a CORS/referrer round-trip from the form.
	"""
	query = ", ".join([p for p in [address, city] if p and p.strip()])
	if not query:
		frappe.throw(_("Enter an address or city first"))

	try:
		response = requests.get(
			NOMINATIM_URL,
			params={"q": query, "format": "json", "limit": 1},
			headers={"User-Agent": "sports-complex-app/1.0 (Frappe; geocode_venue_address)"},
			timeout=8,
		)
		response.raise_for_status()
		results = response.json()
	except requests.RequestException:
		frappe.throw(_("Could not reach the map lookup service. Please try again."))

	if not results:
		frappe.throw(_("No location found for '{0}'. Try a more specific address.").format(query))

	match = results[0]
	return {
		"lat": float(match["lat"]),
		"lon": float(match["lon"]),
		"display_name": match.get("display_name"),
	}
