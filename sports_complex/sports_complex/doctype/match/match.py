# Copyright (c) 2026, Sports Complex and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class Match(Document):
	def validate(self):
		self.enforce_one_match_per_fixture()

	def enforce_one_match_per_fixture(self):
		existing = frappe.db.get_value(
			"Match", {"fixture": self.fixture, "name": ["!=", self.name or ""]}, "name"
		)
		if existing:
			frappe.throw(_("Fixture {0} already has a Match: {1}").format(self.fixture, existing))
