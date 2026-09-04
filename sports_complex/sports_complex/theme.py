# Copyright (c) 2026, Your Company and contributors
# For license information, please see license.txt

"""Theme color + app logo for the guest booking flow's public pages
(facilities, book-facility, my-bookings, booking-confirmation, portal).

Configured via Sports Complex Setup > Website > Theme Color (a Color
field), so a manager can rebrand the booking flow without touching code.
Every page that used to hardcode the green (#16a34a / #15803d hover /
rgba(22, 163, 74, ...) tints) instead pulls these values in via CSS
custom properties injected from get_theme_context(), scoped to that
page's own root element - see the "--sc-primary*" declarations near the
top of each page's <style> block.
"""

import base64
import mimetypes
import re

import frappe

DEFAULT_THEME_COLOR = "#16a34a"

# How much darker the hover shade is than the base color (0-1). Chosen to
# land close to the original hardcoded pair (#16a34a -> #15803d is what
# this app used everywhere before the color became configurable).
HOVER_DARKEN_AMOUNT = 0.18

_HEX_RE = re.compile(r"^[0-9a-fA-F]{6}$")


def get_theme_context():
	"""Dict of Jinja context vars for the theme color. Always returns
	usable values - an unset or malformed Theme Color falls back to the
	original green, so this is a no-op for sites that haven't configured
	it yet."""
	configured = frappe.db.get_single_value("Sports Complex Setup", "theme_color")
	rgb = _hex_to_rgb(configured) or _hex_to_rgb(DEFAULT_THEME_COLOR)
	hover_rgb = _darken(rgb, HOVER_DARKEN_AMOUNT)
	return {
		"theme_color": _rgb_to_hex(rgb),
		"theme_color_hover": _rgb_to_hex(hover_rgb),
		"theme_color_rgb": "{}, {}, {}".format(*rgb),
		"app_name": get_company_name(),
	}


def get_company_name():
	"""The real-world business name, for anywhere the site would otherwise
	hardcode "Sports Complex" (the app's own generic/internal name) - the
	Navbar, Login page, browser tab title, etc. Sourced from Sports
	Complex Setup's own Default Company (already configured there for
	invoicing - see doctype/sports_complex_setup), falling back to the
	site's global default company, and finally to the app's generic name
	if neither is set so every caller always gets a usable string back.
	"""
	company = frappe.db.get_single_value("Sports Complex Setup", "default_company")
	if not company:
		company = frappe.defaults.get_global_default("company")
	if company:
		company_name = frappe.db.get_value("Company", company, "company_name")
		if company_name:
			return company_name
	return "Sports Complex"


def _hex_to_rgb(value):
	if not value:
		return None
	value = value.strip().lstrip("#")
	if len(value) == 3:
		value = "".join(ch * 2 for ch in value)
	if not _HEX_RE.match(value):
		return None
	return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))


def _rgb_to_hex(rgb):
	return "#{:02x}{:02x}{:02x}".format(*(max(0, min(255, int(round(c)))) for c in rgb))


def _darken(rgb, amount):
	return tuple(c * (1 - amount) for c in rgb)


def get_app_logo_data_uri():
	"""Read the site's configured App Logo (Website Settings > App Logo)
	and inline it as a data: URI instead of pointing an <img> at its
	file_url - moved here from www/facilities/index.py so www/portal/
	index.py can reuse the exact same logic instead of a second copy.

	The App Logo is commonly uploaded as a private file (as it is on this
	site: /private/files/...), and Frappe serves private files through a
	route that checks the requesting user's permissions - a guest on a
	public booking page gets a 403 for that URL, same as anyone else who
	isn't logged in would on the login page's own logo. Reading the bytes
	here happens server-side during page render, before any browser
	request for the image URL exists, so that permission check never
	comes into play - this works whether the file is public or private,
	with no need to change how it's stored.
	"""
	file_url = frappe.db.get_single_value("Website Settings", "app_logo")
	if not file_url:
		return None
	try:
		file_doc = frappe.get_doc("File", {"file_url": file_url})
		content = file_doc.get_content()
		mime_type = mimetypes.guess_type(file_doc.file_name or file_url)[0] or "image/png"
		return f"data:{mime_type};base64,{base64.b64encode(content).decode()}"
	except Exception:
		frappe.log_error(title="Sports Complex: failed to load app logo")
		return None
