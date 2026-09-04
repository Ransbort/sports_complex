# Copyright (c) 2026, Sports Complex and contributors
# For license information, please see license.txt

"""Shell page for the Vue Portal SPA (sports_complex/frontend - see that
directory's own README.md for the full picture). This page itself renders
almost nothing - just a <div id="app"> and a bit of boot context - and
Vue Router takes over from there client-side. hooks.py's website_route_
rules sends every /portal/<anything> request here too (not just the bare
/portal), so a hard reload or a shared link to a nested route like
/portal/book-coach still renders this same shell instead of 404ing before
Vue Router gets a chance to pick up that path.

Deliberately no require_portal_login() - same reasoning as book-facility/
book-coach/tournaments/index.py: guest booking has to keep working from
inside this app too, so is_guest is just context for the frontend to
branch on, never a gate here.
"""

import frappe

from sports_complex.sports_complex.theme import get_app_logo_data_uri, get_theme_context


def get_context(context):
	context.title = "Sports Complex"
	is_guest = frappe.session.user == "Guest"

	currency = frappe.defaults.get_global_default("currency") or "USD"
	currency_symbol = frappe.db.get_value("Currency", currency, "symbol") or currency

	theme = get_theme_context()

	full_name = None
	if not is_guest:
		full_name = frappe.db.get_value("User", frappe.session.user, "full_name")

	# Same shared logo lookup as www/facilities/index.py - see theme.py's
	# get_app_logo_data_uri() docstring for why this is inlined as a
	# data: URI rather than a plain file_url.
	app_logo = get_app_logo_data_uri()

	# One JSON blob rather than a handful of separate context.*_json vars
	# (contrast the legacy pages) - the SPA reads this once, in main.js's
	# own stores/auth.js, instead of every page needing its own server-
	# rendered payload the way each old www/<page>/index.py did.
	context.portal_boot_json = frappe.as_json(
		{
			"is_guest": is_guest,
			"user": frappe.session.user,
			"full_name": full_name,
			"currency_symbol": currency_symbol,
			"app_logo": app_logo,
			**theme,
		}
	)
	context.update(theme)
	return context
