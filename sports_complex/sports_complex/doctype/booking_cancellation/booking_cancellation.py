# Copyright (c) 2026, Your Company and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class BookingCancellation(Document):
	def validate(self):
		booking_status = frappe.db.get_value("Facility Booking", self.facility_booking, "booking_status")
		if booking_status in ("Cancelled", "Completed"):
			frappe.throw(
				_("Facility Booking {0} cannot be cancelled (current status: {1})").format(
					self.facility_booking, booking_status
				)
			)

	def on_submit(self):
		frappe.db.set_value("Facility Booking", self.facility_booking, "booking_status", "Cancelled")

		if self.refund_amount:
			self.create_credit_note()
			self.db_update()

	def on_cancel(self):
		# Reverting the cancellation of a cancellation: leave the Facility
		# Booking's status alone here, since it may already have moved on
		# (e.g. rebooked). Handle manually if needed.
		pass

	def create_credit_note(self):
		"""Create a Return-type Sales Invoice against the booking's original invoice.

		Uses ERPNext's standard sales return helper so tax/stock/accounting
		implications are handled the same way as any other credit note.
		"""
		if self.credit_note:
			return

		original_invoice = frappe.db.get_value("Facility Booking", self.facility_booking, "sales_invoice")
		if not original_invoice:
			frappe.throw(
				_("Facility Booking {0} has no linked Sales Invoice to refund against").format(
					self.facility_booking
				)
			)

		from erpnext.accounts.doctype.sales_invoice.sales_invoice import make_sales_return

		credit_note = frappe.get_doc(make_sales_return(original_invoice))
		credit_note.flags.ignore_permissions = True
		credit_note.insert()
		credit_note.submit()

		self.credit_note = credit_note.name
		self.refund_status = "Processed"
