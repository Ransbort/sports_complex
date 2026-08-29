# Copyright (c) 2026, Your Company and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, get_datetime, time_diff_in_hours

from sports_complex.utils.invoicing import get_default_company, get_income_account, get_receivable_account


class CheckOut(Document):
	def validate(self):
		booking = frappe.db.get_value(
			"Facility Booking",
			self.facility_booking,
			["booking_status", "booking_date", "end_time", "rate"],
			as_dict=True,
		)
		if not booking:
			frappe.throw(_("Facility Booking {0} not found").format(self.facility_booking))
		if booking.booking_status != "Checked-In":
			frappe.throw(
				_("Facility Booking {0} must be Checked-In before check-out (current status: {1})").format(
					self.facility_booking, booking.booking_status
				)
			)

		self.calculate_overage(booking)

	def calculate_overage(self, booking):
		check_in_time = frappe.db.get_value(
			"Check-In", {"facility_booking": self.facility_booking, "docstatus": 1}, "check_in_time"
		)
		if not check_in_time or not self.check_out_time:
			return

		self.actual_duration = int(
			round(time_diff_in_hours(get_datetime(self.check_out_time), get_datetime(check_in_time)) * 60)
		)

		scheduled_end = get_datetime(f"{booking.booking_date} {booking.end_time}")
		overage_minutes = int(round(time_diff_in_hours(get_datetime(self.check_out_time), scheduled_end) * 60))
		self.overage_minutes = overage_minutes if overage_minutes > 0 else 0

		if self.overage_minutes and booking.rate:
			self.overage_charge = flt(booking.rate) * (self.overage_minutes / 60)
		else:
			self.overage_charge = 0

	def on_submit(self):
		frappe.db.set_value("Facility Booking", self.facility_booking, "booking_status", "Completed")

		if self.overage_charge:
			self.create_overage_invoice()
			self.db_update()

	def on_cancel(self):
		frappe.db.set_value("Facility Booking", self.facility_booking, "booking_status", "Checked-In")

	def create_overage_invoice(self):
		"""Bill overage time as an additional Sales Invoice.

		NOTE: assumes a generic sellable Item named "Facility Overage" exists.
		Create it once (Item Group: Facility Usage) or adjust the item_code
		below to match your actual catalogue.
		"""
		if self.overage_sales_invoice:
			return

		if not frappe.db.exists("Item", "Facility Overage"):
			frappe.throw(
				_(
					"No 'Facility Overage' Item found. Create a sellable Item with that "
					"name before submitting a Check-Out with overage charges."
				)
			)

		customer = frappe.db.get_value("Facility Booking", self.facility_booking, "customer")
		company = get_default_company()

		si = frappe.new_doc("Sales Invoice")
		si.customer = customer
		si.facility_booking = self.facility_booking
		if company:
			si.company = company
			receivable_account = get_receivable_account(company)
			if receivable_account:
				si.debit_to = receivable_account

		item_row = {
			"item_code": "Facility Overage",
			"qty": 1,
			"rate": self.overage_charge,
		}
		income_account = get_income_account(company)
		if income_account:
			item_row["income_account"] = income_account

		si.append(
			"items",
			item_row,
		)
		si.flags.ignore_permissions = True
		si.insert()

		self.overage_sales_invoice = si.name
