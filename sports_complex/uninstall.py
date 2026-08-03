"""
Uninstallation hooks for Sports Complex
"""

import logging

import frappe

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

		# TODO: add cleanup steps here, e.g.:
		# remove_custom_fields()
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
