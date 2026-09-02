# Copyright (c) 2026, Sports Complex and contributors
# For license information, please see license.txt

"""One-off cleanup for a *different* duplicate-Lab-Test bug than
dedupe_trial_lab_panel.py handles - this one affects ordinary doctor-ordered
(encounter-sourced) lab requests, not the trial screening panel.

Root cause (fixed alongside this script - see accept_lab_request() in
lab_portal.py): that function used to bill the Sales Invoice against
reference_dt="Lab Prescription". Core Healthcare's own Sales Invoice
on_submit hook (manage_invoice_submit_cancel() -> create_multiple(), gated
on Healthcare Settings' "Create Lab Test on Sales Invoice Submit") scans
every submitted invoice for line items whose Item Code matches a Lab Test
Template, and only skips creating its OWN Lab Test for that line when it
finds reference_dt == "Lab Test" already. "Lab Prescription" didn't match,
so every single accepted request silently got a SECOND, untracked Lab Test
made for it the moment its invoice was submitted - invoiced=1, no
custom_invoice (core doesn't know about this app's own field) - which Lab
Portal then showed as a "Free" duplicate card the instant the request moved
from Requested Labs into Pending Labs. Core also quietly re-points the
Sales Invoice Item's own reference at this new phantom Lab Test instead of
the one this app actually created and is tracking via custom_invoice.

This script only touches a Lab Test when it can positively confirm that
exact shape - never a guess by patient/template/timing alone:

  1. Candidate: invoiced=1, custom_invoice unset, prescription unset,
     sc_trial_appointment unset, not Cancelled, not cancelled-docstatus.
     (sc_trial_appointment unset rules out a legitimate free trial-panel
     test - see dedupe_trial_lab_panel.py - which this script never
     touches.)
  2. Find the real Sales Invoice Item that core re-pointed at this
     candidate (reference_dt="Lab Test", reference_dn=candidate).
  3. On that SAME invoice, find the sibling Lab Test this app actually
     created and is tracking (custom_invoice = that invoice). If there
     isn't exactly one, the candidate is left alone for manual review -
     this script never deletes anything it can't positively explain.
  4. Only once both are confirmed: repair the Sales Invoice Item to point
     back at the real sibling Lab Test, THEN delete the now-unlinked
     phantom. Deleting first (without the repair) would fail with Frappe's
     own LinkExistsError, same as it did the first time this was tried
     against the trial-panel version of this bug.

A candidate with no Sales Invoice Item link at all, or one whose invoice
doesn't have a matching tracked sibling, is reported but left untouched -
this script never deletes a Lab Test it can't positively attribute to a
real, still-tracked sibling.

Usage - dry run first (reports what it WOULD do, changes nothing):
  bench --site erp.pepsportslimited.com execute \\
      sports_complex.utils.dedupe_encounter_lab_duplicates.execute

Then, once you've reviewed the report, actually apply it:
  bench --site erp.pepsportslimited.com execute \\
      sports_complex.utils.dedupe_encounter_lab_duplicates.execute \\
      --kwargs "{'dry_run': False}"
"""

import frappe


def execute(dry_run=True):
	"""Find, and (only when dry_run=False) repair-then-remove, phantom
	encounter-sourced Lab Test duplicates. Always prints a report; also
	returns it as a list of dicts for programmatic use.
	"""
	candidates = frappe.get_all(
		"Lab Test",
		filters={
			"invoiced": 1,
			"custom_invoice": ["is", "not set"],
			"prescription": ["is", "not set"],
			"sc_trial_appointment": ["is", "not set"],
			"status": ["!=", "Cancelled"],
			"docstatus": ["!=", 2],
		},
		fields=["name", "patient", "patient_name", "template", "creation"],
		order_by="creation asc",
	)

	report = []

	for candidate in candidates:
		entry = {
			"patient": candidate.patient,
			"patient_name": candidate.patient_name,
			"template": candidate.template,
			"duplicate": candidate.name,
			"duplicate_created": str(candidate.creation),
		}

		invoice_item = frappe.db.get_value(
			"Sales Invoice Item",
			{"reference_dt": "Lab Test", "reference_dn": candidate.name, "docstatus": ["!=", 2]},
			["name", "parent"],
			as_dict=True,
		)
		if not invoice_item:
			entry["action"] = "SKIPPED - no linked Sales Invoice Item found, needs manual review"
			report.append(entry)
			continue

		entry["invoice"] = invoice_item.parent

		sibling = frappe.get_all(
			"Lab Test",
			filters={"custom_invoice": invoice_item.parent, "name": ["!=", candidate.name]},
			fields=["name"],
			limit=2,
		)
		if len(sibling) != 1:
			entry["action"] = (
				f"SKIPPED - {'no' if not sibling else 'more than one'} tracked sibling Lab Test found "
				f"on invoice {invoice_item.parent}, needs manual review"
			)
			report.append(entry)
			continue

		entry["kept"] = sibling[0].name

		if dry_run:
			entry["action"] = (
				f"would repair Sales Invoice Item {invoice_item.name} to point at "
				f"{sibling[0].name}, then delete (dry run)"
			)
		else:
			try:
				frappe.db.set_value(
					"Sales Invoice Item",
					invoice_item.name,
					{"reference_dt": "Lab Test", "reference_dn": sibling[0].name},
				)
				frappe.delete_doc("Lab Test", candidate.name, ignore_permissions=True)
				entry["action"] = f"repaired Sales Invoice Item {invoice_item.name}, deleted"
			except Exception as e:
				# Never let one unexpected condition abort the whole batch -
				# report it and move on to the rest.
				entry["action"] = f"SKIPPED - could not repair/delete ({e})"

		report.append(entry)

	if not dry_run:
		frappe.db.commit()

	mode = "DRY RUN - nothing changed" if dry_run else "APPLIED"
	print(f"\n=== Encounter-sourced lab test duplicate cleanup ({mode}) ===")
	if not report:
		print("No matching duplicates found.")
	for entry in report:
		kept = f" -> kept {entry['kept']}" if entry.get("kept") else ""
		invoice = f" [invoice {entry['invoice']}]" if entry.get("invoice") else ""
		print(
			f"{entry['patient_name']} ({entry['patient']}) - {entry['template']}: "
			f"duplicate {entry['duplicate']} (created {entry['duplicate_created']}){kept}{invoice} "
			f"[{entry['action']}]"
		)

	fixed_count = sum(1 for e in report if e["action"].startswith("repaired"))
	skipped_count = len(report) - fixed_count
	if dry_run:
		print(f"\nTotal: {len(report)} duplicate(s) found.")
	else:
		print(f"\nTotal: {len(report)} duplicate(s) found - {fixed_count} repaired+removed, {skipped_count} skipped (see above).")

	return {"report": report}
