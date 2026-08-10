# Copyright (c) 2026, Pep Sports Limited and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, today


class Player(Document):
	def validate(self):
		self.set_full_name()
		self.set_age()

	def set_full_name(self):
		self.full_name = " ".join(
			part for part in [self.first_name, self.middle_name, self.last_name] if part
		).strip()

	def set_age(self):
		self.age = _format_age(self.date_of_birth)


def _format_age(dob):
	"""Kept identical to Trialist's _format_age() so a player's displayed
	age looks the same before and after conversion — small enough that
	duplicating rather than importing across doctype modules is simpler
	than adding a shared utils module for one helper."""

	if not dob:
		return None

	delta_days = (getdate(today()) - getdate(dob)).days
	years, days = divmod(delta_days, 365)

	year_label = _("year") if years == 1 else _("years")
	day_label = _("day") if days == 1 else _("days")

	return _("{0} {1}, {2} {3} old").format(years, year_label, days, day_label)
