"""
Installation and Migration hooks for Sports Complex

This module relies on Frappe's fixture system for:
- Custom fields (custom_field.json)
- Roles (role.json)
- Custom DocPerm (custom_docperm.json)
- Print formats (print_format.json)

Fixtures are defined in hooks.py and synced automatically during install/migrate.
This module handles post-fixture tasks (setting defaults, clearing cache, etc).
Add app-specific setup steps inside after_install / after_migrate as needed.
"""

import logging

import frappe

# Configure logger
logger = logging.getLogger(__name__)


def after_install():
	"""Hook that runs after app installation"""
	try:
		log_message("Sports Complex: Running post-install setup", level="info")

		# TODO: add post-install setup steps here (e.g. default records,
		# default settings, seeding reference data)

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
		# TODO: add post-migrate steps here (e.g. re-syncing defaults that
		# other apps may have overwritten, backfilling new fields)

		# Clear cache
		frappe.clear_cache()
		frappe.db.commit()

		log_message("Sports Complex: Migration completed successfully", level="success")
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(title="Sports Complex Migration Error", message=frappe.get_traceback())
		log_message(f"Sports Complex: Migration error - {str(e)}", level="error")
		raise


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
