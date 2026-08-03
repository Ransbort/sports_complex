# Copyright (c) 2026, Sports Complex and contributors
# For license information, please see license.txt

from datetime import date

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate


class PlayerRegistration(Document):
	def validate(self):
		self.set_age_and_minor_flag()
		self.validate_guardian_consent()

	def set_age_and_minor_flag(self):
		if not self.date_of_birth:
			return

		dob = getdate(self.date_of_birth)
		today = date.today()
		age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))

		self.age = age
		self.is_minor = 1 if age < 18 else 0

	def validate_guardian_consent(self):
		"""Guardian details and consent are mandatory before a minor's
		registration can be saved as active."""
		if not self.is_minor:
			return

		missing = []
		if not self.guardian_name:
			missing.append(_("Guardian Name"))
		if not self.guardian_contact:
			missing.append(_("Guardian Contact"))
		if not self.consent_given:
			missing.append(_("Consent Given"))
		if not self.consent_date:
			missing.append(_("Consent Date"))

		if missing:
			frappe.throw(
				_(
					"This player is a minor. The following guardian/consent fields "
					"are mandatory before saving: {0}"
				).format(", ".join(missing))
			)
