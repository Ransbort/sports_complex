# Copyright (c) 2026, Your Company
# License: MIT

import re

import frappe
import requests
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_time

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

# Matches a Google "Plus Code" / Open Location Code grid reference like
# "V9M7+PG" or the longer "8FVC9G8F+6X" form. Nominatim indexes OpenStreetMap
# tags, not Google's Plus Code grid - it has no idea what to do with this
# token, and including it alongside an unrelated business name in one query
# (e.g. "V9M7+PG Pep Sports Limited, Asamankese") reliably returns zero
# results even though Google's own Plus Code resolver (a different service
# entirely) can resolve the code fine on its own. Stripping it out before
# querying is what actually fixes the lookup, rather than the error
# message's "try a more specific address" suggesting the address itself is
# somehow too vague.
PLUS_CODE_RE = re.compile(r"\b[0-9A-Za-z]{4,8}\+[0-9A-Za-z]{2,3}\b")


class Venue(Document):
	def validate(self):
		if self.operating_hours_from and self.operating_hours_to:
			# operating_hours_from/to are Time fields, but Frappe doesn't
			# consistently hand them to validate() as timedelta/time objects
			# - a doc arriving fresh from the client's Save call can carry
			# them as plain "HH:MM:SS" strings instead. Comparing those with
			# a bare >= does a STRING comparison, not a time comparison, and
			# "9:00:00" >= "18:00:00" is True lexicographically (the
			# character '9' sorts after '1') even though 9am is obviously
			# before 6pm - which is exactly the false positive this threw
			# for a 09:00-18:00 range. get_time() normalizes either
			# representation (string, timedelta, datetime.time) into a
			# proper datetime.time first, so the comparison is always
			# numeric regardless of which form the value happens to be in.
			if get_time(self.operating_hours_from) >= get_time(self.operating_hours_to):
				frappe.throw(
					_("Operating Hours From ({0}) must be earlier than Operating Hours To ({1})").format(
						self.operating_hours_from, self.operating_hours_to
					)
				)


def _nominatim_search(query):
	response = requests.get(
		NOMINATIM_URL,
		params={"q": query, "format": "json", "limit": 1},
		headers={"User-Agent": "sports-complex-app/1.0 (Frappe; geocode_venue_address)"},
		timeout=8,
	)
	response.raise_for_status()
	return response.json()


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

	Tries progressively broader queries so a Plus Code or an
	unrecognised business name in the address doesn't sink the whole
	lookup: (1) the full address + city as typed, (2) the same with any
	Plus Code token stripped out, (3) city alone, which at worst lands
	the pin on the town center for the admin to drag into place - already
	the documented fallback for the Location field. Anything past
	attempt (1) is flagged "approximate" in the response so the caller
	can tell the admin to double-check pin placement.
	"""
	address = (address or "").strip()
	city = (city or "").strip()

	if not address and not city:
		frappe.throw(_("Enter an address or city first"))

	stripped_address = PLUS_CODE_RE.sub("", address).strip(" ,")

	attempts = []
	full_query = ", ".join([p for p in [address, city] if p])
	attempts.append((full_query, False))
	if stripped_address != address:
		stripped_query = ", ".join([p for p in [stripped_address, city] if p])
		if stripped_query and stripped_query != full_query:
			attempts.append((stripped_query, True))
	if city and city != full_query:
		attempts.append((city, True))

	last_query = full_query
	for query, approximate in attempts:
		if not query:
			continue
		last_query = query
		try:
			results = _nominatim_search(query)
		except requests.RequestException:
			frappe.throw(_("Could not reach the map lookup service. Please try again."))

		if results:
			match = results[0]
			return {
				"lat": float(match["lat"]),
				"lon": float(match["lon"]),
				"display_name": match.get("display_name"),
				"approximate": approximate,
			}

	frappe.throw(_("No location found for '{0}'. Try a more specific address.").format(last_query))
