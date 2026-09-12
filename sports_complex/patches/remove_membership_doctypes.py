# Copyright (c) 2026, Your Company
# License: MIT

"""Retires the Membership module: Membership, Membership Plan, Membership
Plan Facility Type (Membership Plan's own child table), Membership
Renewal, and Member Attendance.

None of these are being ported to the Vue Portal SPA, and the
corresponding sc-source Sales Invoice back-link fields (membership,
membership_renewal) plus the Membership tab on Sports Complex Setup
(renewal_grace_period_days, auto_suspend_on_expiry, renewal_reminder_
days_before - unused elsewhere in the codebase even before this) have
already been removed from disk by the schema/fixture sync that runs
before this (post_model_sync) patch. What's left is dropping the
doctypes themselves (and their tables) from any site that already has
this app installed.

Deliberately NOT touched:
  - Member: the core guest/customer identity doctype every booking flow
    (guest_booking.resolve_or_create_guest_customer, Trialist, Player
    Registration) creates and links against - nothing to do with a paid
    Membership subscription despite the similar name. Its read-only
    `membership_status` Select field (Active/Expired/Suspended) is left
    in place too: it's a plain field, not a Link, so removing Membership
    doesn't break its schema - it just stops being updated by anything
    (Membership/Membership Renewal were the only code that ever set it).
  - Team Member: Coaching module's Team roster child table, unrelated to
    Membership despite the similar name.

Back up the database before running `bench migrate` with this patch -
the DocType deletions below are destructive (DROP TABLE) and this has not
been tested against a live site.
"""

import frappe

DOCTYPES_TO_REMOVE = [
	"Membership Renewal",
	"Membership Plan Facility Type",
	"Membership Plan",
	"Membership",
	"Member Attendance",
]

# Sales Invoice Custom Fields that only ever backed the doctypes above.
# fixtures/custom_field.json no longer declares these, but removing them
# from disk doesn't retroactively delete the Custom Field records a
# site's earlier migrate already created.
OBSOLETE_SALES_INVOICE_CUSTOM_FIELDS = [
	"membership",
	"membership_renewal",
]


def execute():
	for doctype in DOCTYPES_TO_REMOVE:
		if not frappe.db.exists("DocType", doctype):
			# Nothing to migrate - either a fresh install (never existed)
			# or this patch already ran.
			continue
		frappe.delete_doc("DocType", doctype, ignore_permissions=True, force=True)

	if OBSOLETE_SALES_INVOICE_CUSTOM_FIELDS:
		frappe.db.delete(
			"Custom Field",
			{
				"dt": "Sales Invoice",
				"fieldname": ("in", OBSOLETE_SALES_INVOICE_CUSTOM_FIELDS),
			},
		)
		frappe.clear_cache(doctype="Sales Invoice")

	frappe.db.commit()
