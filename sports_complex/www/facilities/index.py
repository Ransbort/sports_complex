# Copyright (c) 2026, Your Company and contributors
# For license information, please see license.txt

import base64
import mimetypes

import frappe

from sports_complex.sports_complex.theme import get_theme_context


def get_context(context):
	context.title = "Sports Complex"
	# Pure navigation hub to /book-facility and /my-bookings - no
	# user-specific data needed, so no is_guest branching or API calls
	# here (contrast book-facility/my-bookings's index.py).

	# The site's own configured logo (Website Settings > App Logo), so the
	# hero shows the real company logo instead of a generic trophy icon.
	# Falls back to the icon in the template if no logo has been uploaded
	# or it can't be read for any reason.
	context.app_logo = get_app_logo_data_uri()
	context.update(get_theme_context())
	return context


def get_app_logo_data_uri():
	"""Read the configured App Logo and inline it as a data: URI instead
	of pointing the <img> at its file_url.

	The App Logo is commonly uploaded as a private file (as it is on this
	site: /private/files/...), and Frappe serves private files through a
	route that checks the requesting user's permissions - a guest on this
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
		frappe.log_error(title="Sports Complex: failed to load app logo for /facilities")
		return None
