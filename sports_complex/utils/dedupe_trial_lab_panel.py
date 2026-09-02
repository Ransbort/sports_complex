# Copyright (c) 2026, Sports Complex and contributors
# For license information, please see license.txt

"""One-off cleanup for the trial-lab-panel duplicate-creation bug (fixed
alongside this script - see create_trial_lab_panel() in
healthcare_integration.py): a patient routed through the trial vitals flow
more than once - a second Trial Appointment, or a repeated call for the
same one - ended up with two open Lab Test records for the same template:
one from the earlier trial visit, one freshly auto-created and marked Free.

Deliberately narrow about what it will actually remove. A duplicate is only
ever auto-deleted when it is BOTH:
  - trial-panel-sourced (sc_trial_appointment is set) - never an ordinary
    doctor-ordered Lab Prescription/direct request, paid or not - and is
    only ever compared against OTHER trial-panel-sourced Lab Tests, never
    against a doctor's own Patient Encounter order. Trial screening and a
    doctor's own clinical order are separate requests for separate
    reasons; sharing an Item Template name (e.g. "Typhoid") doesn't make
    them duplicates of each other, and this script never treats them as
    such in either direction;
  - still completely untouched: status "Draft" and docstatus 0 - never
    submitted, never had results entered, never reviewed.

Anything that doesn't meet both of those (a duplicate that's already been
submitted, has progressed past Draft, or has results on it) is reported but
left alone for manual review - this script never cancels a submitted Lab
Test and never touches anything with real clinical data on it.

"Already covered" means an earlier (by creation date), non-cancelled,
trial-panel-sourced Lab Test exists for the same Patient + Item Template -
matching exactly what the fixed create_trial_lab_panel() now checks, so
this cleans up the backlog the old, narrower (this-appointment-only) check
let through.

Usage - dry run first (reports what it WOULD do, changes nothing):
  bench --site erp.pepsportslimited.com execute \\
      sports_complex.utils.dedupe_trial_lab_panel.execute

Then, once you've reviewed the report, actually apply it:
  bench --site erp.pepsportslimited.com execute \\
      sports_complex.utils.dedupe_trial_lab_panel.execute \\
      --kwargs "{'dry_run': False}"
"""

import frappe


def execute(dry_run=True):
	"""Find, and (only when dry_run=False) remove, duplicate trial-panel
	Lab Tests. Always prints a report; also returns it as a list of dicts
	for programmatic use.
	"""
	candidates = frappe.get_all(
		"Lab Test",
		filters={
			"sc_trial_appointment": ["is", "set"],
			"status": "Draft",
			"docstatus": 0,
		},
		fields=["name", "patient", "patient_name", "template", "creation"],
		order_by="creation asc",
	)

	report = []

	for panel_test in candidates:
		earlier = frappe.get_all(
			"Lab Test",
			filters={
				"patient": panel_test.patient,
				"template": panel_test.template,
				"name": ["!=", panel_test.name],
				"sc_trial_appointment": ["is", "set"],
				"status": ["!=", "Cancelled"],
				"docstatus": ["!=", 2],
				"creation": ["<", panel_test.creation],
			},
			fields=["name", "sc_trial_appointment", "status", "docstatus", "creation"],
			order_by="creation asc",
			limit=1,
		)
		if not earlier:
			continue  # earliest open trial-panel entry for this patient+template - keep it

		kept = earlier[0]
		entry = {
			"patient": panel_test.patient,
			"patient_name": panel_test.patient_name,
			"template": panel_test.template,
			"duplicate": panel_test.name,
			"duplicate_created": str(panel_test.creation),
			"kept": kept.name,
			"kept_source": "trial panel",
			"kept_created": str(kept.creation),
		}

		# Belt-and-braces: a Draft, never-submitted Lab Test can still have
		# been individually invoiced by staff clicking Accept on it at some
		# point (accept_direct_lab_request() only refuses when custom_invoice
		# is already set - a real Sales Invoice Item can still exist even so)
		# - never delete anything with a real Sales Invoice Item pointing at
		# it. Checked unconditionally, dry run or not, so the report always
		# matches what a live run will actually do.
		blocking_invoice = frappe.db.get_value(
			"Sales Invoice Item",
			{"reference_dt": "Lab Test", "reference_dn": panel_test.name, "docstatus": ["!=", 2]},
			"parent",
		)
		if blocking_invoice:
			entry["action"] = f"SKIPPED - linked to Sales Invoice {blocking_invoice}, needs manual review"
		elif dry_run:
			entry["action"] = "would delete (dry run)"
		else:
			try:
				frappe.delete_doc("Lab Test", panel_test.name, ignore_permissions=True)
				entry["action"] = "deleted"
			except Exception as e:
				# Never let one unexpected link (or anything else) abort the
				# whole batch - report it and move on to the rest.
				entry["action"] = f"SKIPPED - could not delete ({e})"

		report.append(entry)

	if not dry_run:
		frappe.db.commit()

	mode = "DRY RUN - nothing changed" if dry_run else "APPLIED"
	print(f"\n=== Trial lab panel duplicate cleanup ({mode}) ===")
	if not report:
		print("No safely-removable duplicates found.")
	for entry in report:
		print(
			f"{entry['patient_name']} ({entry['patient']}) - {entry['template']}: "
			f"duplicate {entry['duplicate']} (created {entry['duplicate_created']}) "
			f"-> kept {entry['kept']} [{entry['kept_source']}, created {entry['kept_created']}] "
			f"[{entry['action']}]"
		)
	removed_count = sum(1 for e in report if e["action"] == "deleted")
	skipped_count = len(report) - removed_count
	if dry_run:
		print(f"\nTotal: {len(report)} duplicate(s) found.")
	else:
		print(f"\nTotal: {len(report)} duplicate(s) found - {removed_count} removed, {skipped_count} skipped (see above).")

	# Duplicates that exist but weren't safe to touch (already submitted,
	# or past Draft/have results) - surfaced separately so they don't get
	# silently missed just because this run only found 0 auto-removable
	# ones.
	flagged = frappe.get_all(
		"Lab Test",
		filters={"sc_trial_appointment": ["is", "set"], "status": ["!=", "Cancelled"], "docstatus": ["!=", 2]},
		fields=["name", "patient", "patient_name", "template", "status", "docstatus", "creation"],
		order_by="creation asc",
	)
	needs_review = []
	for t in flagged:
		if t.status == "Draft" and t.docstatus == 0:
			continue  # already handled above (or wasn't a duplicate at all)
		dup_exists = frappe.db.exists(
			"Lab Test",
			{
				"patient": t.patient,
				"template": t.template,
				"name": ["!=", t.name],
				"sc_trial_appointment": ["is", "set"],
				"status": ["!=", "Cancelled"],
				"docstatus": ["!=", 2],
				"creation": ["<", t.creation],
			},
		)
		if dup_exists:
			needs_review.append(t)

	if needs_review:
		print(f"\n=== {len(needs_review)} duplicate(s) found but NOT auto-removed (need manual review) ===")
		for t in needs_review:
			print(
				f"{t.patient_name} ({t.patient}) - {t.template}: {t.name} "
				f"[status={t.status}, docstatus={t.docstatus}, created={t.creation}]"
			)

	return {"removed": report, "needs_review": needs_review}
