# Copyright (c) 2026, Your Company and contributors
# For license information, please see license.txt

"""Theme color for the guest booking flow's public pages (facilities,
book-facility, my-bookings, booking-confirmation).

Configured via Sports Complex Setup > Website > Theme Color (a Color
field), so a manager can rebrand the booking flow without touching code.
Every page that used to hardcode the green (#16a34a / #15803d hover /
rgba(22, 163, 74, ...) tints) instead pulls these values in via CSS
custom properties injected from get_theme_context(), scoped to that
page's own root element - see the "--sc-primary*" declarations near the
top of each page's <style> block.
"""

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
	}


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
