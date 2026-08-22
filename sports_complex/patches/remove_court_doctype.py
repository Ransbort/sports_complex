# Copyright (c) 2026, Your Company
# License: MIT

"""Retires the Court doctype: Sports Facility is now the sole bookable
unit (a facility used to have one or more Court "units" under it, but in
practice every facility only ever had exactly one, so that extra layer
was pure overhead - see the Sports Facility Court child doctype this
patch also removes, which was a short-lived attempt at bridging the two
before this).

Every doctype that used to Link to Court via a field literally named
"court" keeps that field name (renaming an existing column with live
data is riskier than it's worth), but the field's `options` now point at
Sports Facility instead - that JSON change has already been applied by
the schema sync that runs before this (post_model_sync) patch. What's
left is data: every stored "court" value is still an old Court.name
string (e.g. "Main Basketball Court-1"), which no longer names anything
valid under the new Sports Facility target. This patch:

  1. Merges each Court's own rate/photo/surface type onto its parent
     Sports Facility, wherever the facility doesn't already have its own
     value (an admin's facility-level edit wins over stale Court data).
  2. Rewrites every stored "court" value across the doctypes that used
     to reference Court, from the old Court name to the Sports Facility
     it belonged to.
  3. Removes the now-empty Sports Facility Court child doctype.
  4. Removes the Court doctype itself (and its table).

Back up the database before running `bench migrate` with this patch -
steps 3 and 4 are destructive (DROP TABLE) and this has not been tested
against a live site.
"""

import frappe

# Doctypes whose `court` field used to Link to Court and now Links to
# Sports Facility instead - every stored value in this column needs the
# same old-name -> new-name rewrite.
COURT_REFERENCING_DOCTYPES = [
	"Facility Booking",
	"Maintenance Schedule",
	"Booking Schedule",
	"Match",
	"Fixtures",
	"Training Schedule",
	"Training Session",
]


def execute():
	if not frappe.db.exists("DocType", "Court"):
		# Nothing to migrate - either a fresh install (Court never
		# existed) or this patch already ran.
		return

	courts = frappe.get_all(
		"Court",
		fields=["name", "sports_facility", "surface_type", "hourly_rate", "image"],
	)
	court_to_facility = {c.name: c.sports_facility for c in courts if c.sports_facility}

	# 1. Merge each Court's own fields onto its Sports Facility.
	for court in courts:
		if not court.sports_facility or not frappe.db.exists("Sports Facility", court.sports_facility):
			continue

		facility = frappe.get_doc("Sports Facility", court.sports_facility)
		changed = False
		if not facility.get("surface_type") and court.surface_type:
			facility.surface_type = court.surface_type
			changed = True
		if not facility.hourly_rate and court.hourly_rate:
			facility.hourly_rate = court.hourly_rate
			changed = True
		if not facility.image and court.image:
			facility.image = court.image
			changed = True

		if changed:
			facility.flags.ignore_permissions = True
			facility.save()

	# 2. Rewrite every stored "court" value across dependent doctypes.
	for doctype in COURT_REFERENCING_DOCTYPES:
		if not frappe.db.exists("DocType", doctype):
			continue
		if "court" not in frappe.db.get_table_columns(doctype):
			continue
		for old_name, new_name in court_to_facility.items():
			frappe.db.sql(
				f"update `tab{doctype}` set court = %(new)s where court = %(old)s",  # noqa: S608
				{"new": new_name, "old": old_name},
			)

	frappe.db.commit()

	# 3. Drop the short-lived Sports Facility Court child doctype (only
	# ever populated if a facility was opened and saved between that
	# feature shipping and this patch replacing it).
	if frappe.db.exists("DocType", "Sports Facility Court"):
		frappe.delete_doc("DocType", "Sports Facility Court", ignore_permissions=True, force=True)

	# 4. Court itself is now fully superseded by Sports Facility.
	frappe.delete_doc("DocType", "Court", ignore_permissions=True, force=True)
