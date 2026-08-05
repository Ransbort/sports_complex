# Copyright (c) 2026, Your Company and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, get_datetime, time_diff_in_hours


class FacilityBooking(Document):
	def validate(self):
		self.validate_times()
		self.calculate_duration_and_amount()
		self.validate_court_overlap()
		self.validate_maintenance_overlap()

	def validate_times(self):
		if self.start_time and self.end_time and self.start_time >= self.end_time:
			frappe.throw(_("Start Time must be before End Time"))

	def calculate_duration_and_amount(self):
		if self.start_time and self.end_time:
			# start_time/end_time are timedelta objects on Time fields; combine
			# with booking_date to get a duration in minutes.
			start = get_datetime(f"{self.booking_date} {self.start_time}")
			end = get_datetime(f"{self.booking_date} {self.end_time}")
			hours = time_diff_in_hours(end, start)
			self.duration = int(round(hours * 60))

			if self.rate:
				self.total_amount = flt(self.rate) * hours

	def validate_court_overlap(self):
		if not (self.court and self.booking_date and self.start_time and self.end_time):
			return

		conflicting = frappe.db.sql(
			"""
			select name
			from `tabFacility Booking`
			where court = %(court)s
				and booking_date = %(booking_date)s
				and name != %(name)s
				and docstatus < 2
				and booking_status not in ('Cancelled', 'No-show')
				and start_time < %(end_time)s
				and end_time > %(start_time)s
			limit 1
			""",
			{
				"court": self.court,
				"booking_date": self.booking_date,
				"name": self.name or "",
				"start_time": self.start_time,
				"end_time": self.end_time,
			},
		)
		if conflicting:
			frappe.throw(
				_("Court {0} is already booked for an overlapping time on {1} ({2})").format(
					self.court, self.booking_date, conflicting[0][0]
				)
			)

	def validate_maintenance_overlap(self):
		if not (self.court and self.booking_date and self.start_time and self.end_time):
			return

		sports_facility = frappe.db.get_value("Court", self.court, "sports_facility")

		conflicting = frappe.db.sql(
			"""
			select name
			from `tabMaintenance Schedule`
			where (court = %(court)s or sports_facility = %(sports_facility)s)
				and scheduled_date = %(booking_date)s
				and docstatus = 1
				and status != 'Completed'
				and (
					scheduled_start is null
					or scheduled_end is null
					or (scheduled_start < %(end_time)s and scheduled_end > %(start_time)s)
				)
			limit 1
			""",
			{
				"court": self.court,
				"sports_facility": sports_facility,
				"booking_date": self.booking_date,
				"start_time": self.start_time,
				"end_time": self.end_time,
			},
		)
		if conflicting:
			frappe.throw(
				_("Court {0} has scheduled maintenance overlapping this time on {1} ({2})").format(
					self.court, self.booking_date, conflicting[0][0]
				)
			)

	def on_submit(self):
		self.booking_status = "Confirmed"
		self.create_sales_invoice()
		self.db_update()

	def on_cancel(self):
		self.db_set("booking_status", "Cancelled")

	def create_sales_invoice(self):
		"""Create the linked Sales Invoice that frappe_paystack will take payment against.

		NOTE: this assumes:
		1. Sales Invoice has a custom Link field `facility_booking` (see schema
		   doc section 6 — add via Customize Form or a fixtures JSON).
		2. There is a sellable Item to bill against. For now this looks for an
		   Item named after the Court's Facility Type; adjust once Sports
		   Settings has a proper Item mapping field.
		"""
		if self.sales_invoice:
			return

		facility_type = frappe.db.get_value(
			"Sports Facility",
			frappe.db.get_value("Court", self.court, "sports_facility"),
			"facility_type",
		)

		if not facility_type or not frappe.db.exists("Item", facility_type):
			frappe.throw(
				_(
					"No Item found for Facility Type {0}. Create a sellable Item with that "
					"name (or update create_sales_invoice) before confirming bookings."
				).format(facility_type or "")
			)

		si = frappe.new_doc("Sales Invoice")
		si.customer = self.customer
		si.facility_booking = self.name
		si.append(
			"items",
			{
				"item_code": facility_type,
				"qty": 1,
				"rate": self.total_amount or self.rate or 0,
			},
		)
		si.flags.ignore_permissions = True
		si.insert()

		self.sales_invoice = si.name


@frappe.whitelist()
def get_booking_events(start, end, filters=None):
	"""Feed the Calendar view for Facility Booking.

	Combines booking_date + start_time/end_time into datetimes since the
	doctype stores date and time separately rather than as combined
	datetime fields. Registered in facility_booking.js via
	get_events_method.
	"""
	conditions = ["booking_date between %(start)s and %(end)s"]
	values = {"start": start, "end": end}

	if filters:
		filters = frappe.parse_json(filters)
		if filters.get("court"):
			conditions.append("court = %(court)s")
			values["court"] = filters["court"]
		if filters.get("booking_status"):
			conditions.append("booking_status = %(booking_status)s")
			values["booking_status"] = filters["booking_status"]

	bookings = frappe.db.sql(
		f"""
		select name, customer, court, booking_date, start_time, end_time,
			booking_status, payment_status
		from `tabFacility Booking`
		where {" and ".join(conditions)}
		""",
		values,
		as_dict=True,
	)

	events = []
	for b in bookings:
		events.append(
			{
				"name": b.name,
				"title": f"{b.court} - {b.customer}",
				"start": get_datetime(f"{b.booking_date} {b.start_time}"),
				"end": get_datetime(f"{b.booking_date} {b.end_time}"),
				"status": b.booking_status,
				"payment_status": b.payment_status,
			}
		)
	return events