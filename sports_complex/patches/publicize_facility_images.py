# Copyright (c) 2026, Your Company
# License: MIT

"""One-off cleanup: Sports Facility.image values set before
make_attached_image_public() shipped (see sports_complex/utils/
attachments.py) are still pointing at private File records, which 403 for
a Guest loading the public /book-court grid - the image is set (so the
card shows a blank/broken background instead of the "no photo" icon
placeholder), it just can't actually be fetched without a logged-in
session.

validate() now runs that fix automatically on every future save, but it
only runs on save - it never touched facilities that already had an
image set before this shipped and haven't been edited since. Re-saving
each one here (rather than poking the File table directly) reuses
exactly the same validate() logic already trusted for this instead of
duplicating it, and is safe to run more than once: make_attached_image_
public() is a no-op once a File is already public, and Sports Facility's
own on_update() (sync_time_slots) is an idempotent full-mirror by design.
"""

import frappe


def execute():
	if not frappe.db.exists("DocType", "Sports Facility"):
		return

	facility_names = frappe.get_all(
		"Sports Facility", filters={"image": ("is", "set")}, pluck="name"
	)
	for name in facility_names:
		facility = frappe.get_doc("Sports Facility", name)
		facility.flags.ignore_permissions = True
		facility.save()

	frappe.db.commit()
