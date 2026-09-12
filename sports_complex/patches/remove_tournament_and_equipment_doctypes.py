# Copyright (c) 2026, Your Company
# License: MIT

"""Retires the Events & Tournaments module (Tournament, Tournament
Registration, Fixtures, Match + its Match Official/Match Score Line/Match
Stat child tables, Results, Awards) and the Inventory module (Equipment,
Equipment Issue, Equipment Return).

None of these are being ported to the Vue Portal SPA - see frontend/
README.md - and their public www page (www/tournaments) plus the
corresponding sc-source Sales Invoice back-link fields
(tournament_registration, equipment_issue, equipment_return) have already
been removed from disk by the schema/fixture sync that runs before this
(post_model_sync) patch. What's left is dropping the doctypes themselves
(and their tables) from any site that already has this app installed.

Deliberately NOT touched:
  - Player and Player Registration: Player Registration looks "book a
    player"-specific by name, but it's actually the shared identity/
    billing record training_session.py's _resolve_or_create_player_
    registration() creates for every Book a Coach booking too - deleting
    it would break Book a Coach. Player itself is the Coaching module's
    roster doctype.
  - Player Session and Player Availability: these back the "Book a
    Player" one-on-one booking feature. They were removed in an earlier
    pass and restored - the feature isn't built in Vue yet, but the
    doctypes are being kept for a future pass rather than retired.
  - Player Progress Note: a Coaching-side roster tool (buttons on the
    Player form to log/view a player's development notes), unrelated to
    the public "Book a Player" booking page despite the similar name.

Back up the database before running `bench migrate` with this patch -
the DocType deletions below are destructive (DROP TABLE) and this has not
been tested against a live site.
"""

import frappe

# Doctypes to retire, in child-before-parent order (not that force=True
# strictly requires this, but it mirrors how the data actually nests:
# Match's own child tables first, then Match itself, etc.).
DOCTYPES_TO_REMOVE = [
	# Events & Tournaments
	"Match Official",
	"Match Score Line",
	"Match Stat",
	"Match",
	"Fixtures",
	"Results",
	"Awards",
	"Tournament Registration",
	"Tournament",
	# Inventory
	"Equipment Return",
	"Equipment Issue",
	"Equipment",
]

# Sales Invoice Custom Fields that only ever backed the doctypes above.
# fixtures/custom_field.json no longer declares these, but removing them
# from disk doesn't retroactively delete the Custom Field records a
# site's earlier migrate already created.
OBSOLETE_SALES_INVOICE_CUSTOM_FIELDS = [
	"tournament_registration",
	"equipment_issue",
	"equipment_return",
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
