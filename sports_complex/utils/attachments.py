# Copyright (c) 2026, Your Company
# License: MIT

import frappe


def make_attached_image_public(doc, fieldname):
	"""Attach/Attach Image fields upload as PRIVATE files by default in
	Frappe (the underlying File requires a logged-in session to view).
	That's invisible on the desk - you're always logged in there - but
	breaks silently on any public-facing page: a Guest's <img> or
	background-image request for a private file's URL gets a 403 and
	nothing renders. This is almost certainly why Court/Sports Facility
	photos weren't showing up on the public /book-facility grid.

	Call from validate() on any doctype with a public-facing image field
	(Court.image, Sports Facility.image). Flips the linked File to
	public - which also moves it out of the private files folder and
	updates its file_url - and refreshes doc's own copy of that URL so
	the field doesn't keep pointing at the old private path.

	Looked up by file_url alone (not also attached_to_doctype/name) so
	this doesn't depend on the attachment-reference bookkeeping having
	already caught up to doc's final name on a brand new record.
	"""
	file_url = doc.get(fieldname)
	if not file_url:
		return

	file_name = frappe.db.get_value("File", {"file_url": file_url}, "name")
	if not file_name:
		return

	file_doc = frappe.get_doc("File", file_name)
	if not file_doc.is_private:
		return

	file_doc.is_private = 0
	file_doc.save(ignore_permissions=True)

	if file_doc.file_url and file_doc.file_url != file_url:
		doc.set(fieldname, file_doc.file_url)
