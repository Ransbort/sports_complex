# Copyright (c) 2026, Your Company and contributors
# For license information, please see license.txt

from datetime import timedelta

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, get_datetime, now_datetime

MANAGER_ROLES = {"System Manager", "Sports Complex Manager"}


class BookingCancellation(Document):
	def validate(self):
		booking = frappe.get_doc("Facility Booking", self.facility_booking)
		if booking.booking_status in ("Cancelled", "Completed"):
			frappe.throw(
				_("Facility Booking {0} cannot be cancelled (current status: {1})").format(
					self.facility_booking, booking.booking_status
				)
			)
		self.validate_cancellation_window(booking)

	def validate_cancellation_window(self, booking):
		"""Sports Complex Setup > Default Settings has had a "Cancellation
		Window (hours)" field since this doctype was first built, but
		nothing ever read it - a booking could be cancelled (or, once
		self-service cancellation exists, a customer could request
		cancellation of one) right up to its start time. Managers can
		still override past the window from the desk; this only blocks
		Sports Complex Staff and any future self-service caller.
		"""
		if set(frappe.get_roles()) & MANAGER_ROLES:
			return

		window_hours = flt(frappe.db.get_single_value("Sports Complex Setup", "cancellation_window_hours"))
		if not window_hours or not (booking.booking_date and booking.start_time):
			return

		booking_start = get_datetime(f"{booking.booking_date} {booking.start_time}")
		if now_datetime() > booking_start - timedelta(hours=window_hours):
			frappe.throw(
				_(
					"This booking can no longer be cancelled - cancellations must be made "
					"at least {0} hour(s) before the booking's start time"
				).format(window_hours)
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
