# Copyright (c) 2026, Your Company
# License: MIT

"""
Force-resyncs the "Sports Complex" Workspace's content/links/shortcuts
from the on-disk fixture (sports_complex/sports_complex/workspace/
sports_complex/sports_complex.json) onto the live site record.

Why this is needed: Frappe's standard Workspace fixture sync silently
skips a workspace once it has been edited through the Desk's
drag-and-drop Workspace Editor (to avoid clobbering an admin's manual
customization). This workspace was edited that way at some point during
development, so the last several rounds of doctype removal here (Events
& Tournaments, Inventory, Membership - see
remove_tournament_and_equipment_doctypes.py and
remove_membership_doctypes.py) never actually reached the live Workspace
record even though the on-disk JSON was updated correctly and
`bench migrate` reported "Workspace Sidebar 'Sports Complex'" (our own
custom doctype, synced separately and not subject to this same
skip-if-customized behavior) had synced fine. The visible symptom: "Your
Shortcuts" kept showing a "Tournament" shortcut for a DocType that no
longer exists, throwing DoesNotExistError the moment anyone opened the
Sports Complex workspace.

This patch reads the fixture JSON directly and overwrites content/links/
shortcuts on the live doc unconditionally, so the workspace self-heals on
migrate regardless of whether Frappe's own sync decided to skip it.
"""

import json
import os

import frappe


def execute():
	if not frappe.db.exists("Workspace", "Sports Complex"):
		return

	fixture_path = frappe.get_app_path(
		"sports_complex", "sports_complex", "workspace", "sports_complex", "sports_complex.json"
	)
	if not os.path.exists(fixture_path):
		return

	with open(fixture_path) as f:
		fixture = json.load(f)

	workspace = frappe.get_doc("Workspace", "Sports Complex")
	workspace.content = fixture.get("content")
	workspace.set("links", fixture.get("links") or [])
	workspace.set("shortcuts", fixture.get("shortcuts") or [])
	workspace.save(ignore_permissions=True)
	frappe.db.commit()
