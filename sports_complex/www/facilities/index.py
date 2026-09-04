# Copyright (c) 2026, Your Company and contributors
# For license information, please see license.txt

import frappe

from sports_complex.sports_complex.theme import get_app_logo_data_uri, get_theme_context


def get_context(context):
	context.title = "Sports Complex"
	# Pure navigation hub to /book-facility and /my-bookings - no
	# user-specific data needed, so no is_guest branching or API calls
	# here (contrast book-facility/my-bookings's index.py).

	# The site's own configured logo (Website Settings > App Logo), so the
	# hero shows the real company logo instead of a generic trophy icon.
	# Falls back to the icon in the template if no logo has been uploaded
	# or it can't be read for any reason. Shared with www/portal/index.py
	# via sports_complex.theme.get_app_logo_data_uri() rather than each
	# page keeping its own copy.
	context.app_logo = get_app_logo_data_uri()
	context.update(get_theme_context())
	return context
