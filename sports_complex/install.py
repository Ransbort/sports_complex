"""
Installation and Migration hooks for Sports Complex

This module relies on Frappe's fixture system for:
- Roles (role.json)
- Custom DocPerm (custom_docperm.json)
- Print formats (print_format.json)

Custom fields for the Trials & Player Registration module are created
programmatically via sports_complex.setup.make_custom_fields() instead
(see setup.py) - everything else still goes through fixtures as before.
The configured Trial Appointment Type that drives that same module's
medical-first flow, and the Client Script that hides Patient Encounter's
Fitness Result field for non-trial encounters, are likewise provisioned
programmatically via healthcare_integration.ensure_trial_appointment_type()
and .ensure_fitness_result_visibility_script() - see that module's
docstring for the full flow.

Fixtures are defined in hooks.py and synced automatically during install/migrate.
This module handles post-fixture tasks (setting defaults, clearing cache, etc).
Add app-specific setup steps inside after_install / after_migrate as needed.
"""

import json
import logging
import os

import frappe

from sports_complex.setup import make_custom_fields
from sports_complex.sports_complex.healthcare_integration import (
	ensure_fitness_result_visibility_script,
	ensure_queue_status_with_lab_option,
	ensure_trial_appointment_type,
	ensure_view_lab_results_script,
	remove_lab_dashboard_group_script,
)

# Configure logger
logger = logging.getLogger(__name__)


def after_install():
	"""Hook that runs after app installation"""
	try:
		log_message("Sports Complex: Running post-install setup", level="info")

		sync_workspace_sidebars()
		make_custom_fields()
		ensure_trial_appointment_type()
		ensure_fitness_result_visibility_script()
		ensure_view_lab_results_script()
		ensure_queue_status_with_lab_option()
		remove_global_nav_overrides()

		# Clear cache to ensure changes take effect
		frappe.clear_cache()
		frappe.db.commit()

		log_message("Sports Complex: Installation completed successfully", level="success")
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(title="Sports Complex Installation Error", message=frappe.get_traceback())
		log_message(f"Sports Complex: Installation error - {e!s}", level="error")
		raise


def after_migrate():
	"""Hook that runs after bench migrate"""
	try:
		sync_workspace_sidebars()
		make_custom_fields()
		ensure_trial_appointment_type()
		ensure_fitness_result_visibility_script()
		ensure_view_lab_results_script()
		ensure_queue_status_with_lab_option()
		remove_stale_trial_medical_exam_field()
		remove_lab_dashboard_group_script()
		remove_global_nav_overrides()

		# Clear cache
		frappe.clear_cache()
		frappe.db.commit()

		log_message("Sports Complex: Migration completed successfully", level="success")
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(title="Sports Complex Migration Error", message=frappe.get_traceback())
		log_message(f"Sports Complex: Migration error - {str(e)}", level="error")
		raise


def remove_stale_trial_medical_exam_field():
	"""One-time cleanup: "Trial Medical Exam" (Patient Encounter.
	is_trial_medical_exam) used to be a real, auto-set custom field, but
	was dropped in favor of reading appointment_type directly everywhere
	(see healthcare_integration.py) - it added nothing but a checkbox
	nobody needed to look at. make_custom_fields()/create_custom_fields()
	only ever adds or updates fields still listed in setup.py's
	get_custom_fields() - it never deletes ones that have been removed
	from that list - so without this, sites that had already migrated
	while the field existed would be stuck with a permanently orphaned,
	unused checkbox on the Patient Encounter form. Safe to run on every
	migrate: a no-op once the field's gone.
	"""
	if frappe.db.exists("Custom Field", "Patient Encounter-is_trial_medical_exam"):
		frappe.db.delete(
			"Custom Field",
			{"dt": "Patient Encounter", "fieldname": "is_trial_medical_exam"},
		)
		frappe.clear_cache(doctype="Patient Encounter")
		log_message("Removed stale Patient Encounter.is_trial_medical_exam custom field", level="success")


def remove_global_nav_overrides():
	"""One-time cleanup, kept permanently idempotent: an earlier version
	of this file added a site-wide "My Bookings" Top Bar Item and pointed
	the whole site's Home Page at /facilities via Website Settings (plus
	hooks.py loaded a Login-hiding CSS/JS pair on every public page).
	Website Settings is one global record shared by every app/module on
	this site, not something scoped to sports_complex - so all of that
	leaked into pages that have nothing to do with facility booking.

	This undoes both Website Settings changes; the Login/footer hiding
	is undone simply by hooks.py no longer loading that CSS/JS at all.
	Each of this app's own guest-facing pages (facilities, book-facility,
	my-bookings, booking-confirmation) now carries the equivalent
	Login/footer/nav hiding directly in its own <style>/<script> blocks
	instead, so it only ever affects those four pages.

	Safe to run on every migrate: a no-op once already undone. Note the
	Home Page is cleared back to unset rather than restored to whatever
	it held before this app first touched it - that prior value was never
	captured anywhere durable, only printed to the migrate console at the
	time. If a custom Home Page was configured before, it needs to be set
	again manually from Website Settings in the Desk.
	"""
	settings = frappe.get_single("Website Settings")
	changed = False

	kept_items = [row for row in settings.get("top_bar_items", []) if (row.url or "").rstrip("/") != "/my-bookings"]
	if len(kept_items) != len(settings.get("top_bar_items", [])):
		settings.set("top_bar_items", kept_items)
		changed = True

	if settings.home_page == "facilities":
		settings.home_page = ""
		changed = True

	if not changed:
		return

	settings.flags.ignore_permissions = True
	settings.save(ignore_permissions=True)
	log_message("Removed site-wide My Bookings nav item / Home Page override (now page-scoped instead)", level="success")


def sync_workspace_sidebars():
	"""
	Load Workspace Sidebar fixture JSON files and create/update the
	corresponding DB records.

	Workspace Sidebar is not a standard module-doctype citizen — its JSON
	lives at <app>/workspace_sidebar/*.json, outside the folder structure
	frappe.model.sync scans during bench migrate, so it is never picked up
	automatically the way regular DocType fixtures are. This function does
	that sync explicitly: for each JSON file found, it creates the
	Workspace Sidebar record if missing, or updates an existing one and
	fully replaces its items child table with what's in the file, so a
	stale DB record can never drift from the JSON on disk.
	"""
	app_path = frappe.get_app_path("sports_complex")
	sidebar_dir = os.path.join(app_path, "workspace_sidebar")

	if not os.path.isdir(sidebar_dir):
		log_message(f"No workspace_sidebar directory found at {sidebar_dir}, skipping sync", level="warning")
		return

	item_skip_fields = {"doctype", "parent", "parentfield", "parenttype"}

	for filename in sorted(os.listdir(sidebar_dir)):
		if not filename.endswith(".json"):
			continue

		filepath = os.path.join(sidebar_dir, filename)

		try:
			with open(filepath) as f:
				data = json.load(f)
		except (OSError, json.JSONDecodeError) as e:
			log_message(f"Skipping {filename}: could not parse JSON ({e})", level="error")
			continue

		name = data.get("name") or data.get("title")
		if not name:
			log_message(f"Skipping {filename}: no 'name' or 'title' field", level="warning")
			continue

		doc_fields = {
			"header_icon": data.get("header_icon"),
			"title": data.get("title"),
			"module": data.get("module"),
			"app": data.get("app"),
			"for_user": data.get("for_user"),
			"module_onboarding": data.get("module_onboarding"),
		}

		if frappe.db.exists("Workspace Sidebar", name):
			doc = frappe.get_doc("Workspace Sidebar", name)
			doc.update(doc_fields)
			doc.items = []
			action = "Updated"
		else:
			doc = frappe.new_doc("Workspace Sidebar")
			doc.name = name
			doc.update(doc_fields)
			action = "Created"

		for item in data.get("items", []):
			doc.append("items", {k: v for k, v in item.items() if k not in item_skip_fields})

		doc.flags.ignore_permissions = True
		doc.save(ignore_permissions=True)

		log_message(f"{action} Workspace Sidebar '{name}' from {filename} ({len(doc.items)} items)", level="success")


def log_message(message, level="info", indent=0):
	"""
	Standardized logging function with consistent formatting.

	Args:
		message (str): The message to log
		level (str): Log level - info, success, warning, error
		indent (int): Indentation level (0, 1, 2, etc.)
	"""
	indent_str = "  " * indent

	prefixes = {
		"info": "[INFO]",
		"success": "[SUCCESS]",
		"warning": "[WARNING]",
		"error": "[ERROR]",
	}

	prefix = prefixes.get(level, "[INFO]")
	formatted_message = f"{indent_str}{prefix} {message}"

	# Print to console
	print(formatted_message)

	# Also log to frappe logger
	if level == "error":
		logger.error(message)
	elif level == "warning":
		logger.warning(message)
	else:
		logger.info(message)
