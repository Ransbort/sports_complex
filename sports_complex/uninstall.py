"""
Uninstallation hooks for Sports Complex
"""
import logging
import os

import frappe

from sports_complex.setup import delete_custom_fields, get_custom_fields

# Configure logger
logger = logging.getLogger(__name__)


def before_uninstall():
	"""
	Hook that runs before app uninstallation.
	Cleans up custom fields, print formats, and configurations
	created by this app.
	"""
	try:
		log_message("Starting Sports Complex uninstallation", level="info")

		remove_workspace_sidebars()
		remove_custom_fields()

		# TODO: add further cleanup steps here, e.g.:
		# remove_print_formats()
		# reset_related_doctype_configs()

		# Commit all changes
		frappe.db.commit()

		log_message("Sports Complex uninstalled successfully", level="success")
		log_message("All custom fields and configurations have been removed", level="info")
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(title="Sports Complex Uninstallation Error", message=frappe.get_traceback())
		log_message(f"Error during Sports Complex uninstallation: {e!s}", level="error")
		raise


def remove_workspace_sidebars():
	"""
	Delete Workspace Sidebar records that were created from this app's
	workspace_sidebar/*.json fixtures (see sports_complex.install.sync_workspace_sidebars).
	Matches by the "name" field in each JSON file, not by app/module on the
	DB record, since a record may have been hand-edited since install.
	"""
	import json

	app_path = frappe.get_app_path("sports_complex")
	sidebar_dir = os.path.join(app_path, "workspace_sidebar")

	if not os.path.isdir(sidebar_dir):
		return

	for filename in sorted(os.listdir(sidebar_dir)):
		if not filename.endswith(".json"):
			continue

		filepath = os.path.join(sidebar_dir, filename)

		try:
			with open(filepath) as f:
				data = json.load(f)
		except (OSError, json.JSONDecodeError) as e:
			log_message(f"Skipping {filename} during cleanup: could not parse JSON ({e})", level="warning")
			continue

		name = data.get("name") or data.get("title")
		if not name:
			continue

		if frappe.db.exists("Workspace Sidebar", name):
			frappe.delete_doc("Workspace Sidebar", name, ignore_permissions=True, force=True)
			log_message(f"Removed Workspace Sidebar '{name}'", level="success")


def remove_custom_fields():
	"""
	Delete the custom fields created by sports_complex.setup.make_custom_fields()
	on install/migrate (Trialist/Player links on Sales Invoice, Trialist/
	Fitness Result on Patient Encounter — see setup.py for the full list).
	Reads the same get_custom_fields() definition rather than hardcoding
	fieldnames here, so this stays in sync automatically as fields are
	added to/removed from setup.py going forward.
	"""
	delete_custom_fields(get_custom_fields())
	log_message("Removed custom fields defined in sports_complex.setup", level="success")


def log_message(message, level="info", indent=0):
	"""
	Standardized logging function with consistent formatting
	Args:
		message (str): The message to log
		level (str): Log level - info, success, warning, error
		indent (int): Indentation level (0, 1, 2, etc.)
	"""
	indent_str = "  " * indent
	# Log level prefixes
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
	# Also log to frappe logger with appropriate level
	if level == "error":
		logger.error(message)
	elif level == "warning":
		logger.warning(message)
	elif level == "success":
		logger.info(f"SUCCESS: {message}")
	else:
		logger.info(message)


def validate_uninstall():
	"""
	Validate that uninstall can proceed safely.
	Returns (bool, str): True/False and a reason string.
	Add checks here (e.g. active bookings, open sessions) as needed.
	"""
	try:
		# TODO: add real validation checks here
		return True, "Safe to uninstall"
	except Exception as e:
		return False, f"Validation error: {e!s}"
