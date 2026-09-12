# Copyright (c) 2026, Your Company and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, get_datetime, time_diff_in_hours

from sports_complex.utils.invoicing import (
	cancel_linked_invoice,
	make_linked_sales_invoice,
)


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
		cancel_linked_invoice(self.overage_sales_invoice)

	def create_overage_invoice(self):
		"""Bill overage time as an additional Sales Invoice, via the same
		make_linked_sales_invoice() helper Facility Booking/Training Session/
		Trialist all use (see utils/invoicing.py) - which auto-creates the
		"Facility Overage" Item (Item Group: "Facility Usage") the first time
		it's needed, via get_or_create_item(), instead of requiring it to
		already exist on the site.

		This used to build the Sales Invoice by hand and throw "No 'Facility
		Overage' Item found" if that Item was missing - a one-time setup trap
		every fresh site hit the first time it billed overage, since nothing
		else in this app ever creates Items that way; every other billing
		path (Facility Booking, Training Session, Trialist) goes through
		make_linked_sales_invoice() and gets the Item auto-provisioned for
		free.
		"""
		if self.overage_sales_invoice:
			return

		customer = frappe.db.get_value("Facility Booking", self.facility_booking, "customer")

		si = make_linked_sales_invoice(
			customer,
			"Facility Overage",
			"Facility Usage",
			self.overage_charge,
			"facility_booking",
			self.facility_booking,
			description=_("Facility overage charge"),
		)
		si.flags.ignore_permissions = True
		si.submit()

		self.overage_sales_invoice = si.name
