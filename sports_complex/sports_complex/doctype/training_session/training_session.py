# Copyright (c) 2026, Sports Complex and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from sports_complex.sports_complex.utils import get_member_customer, make_linked_sales_invoice


class TrainingSession(Document):
	def validate(self):
		self.validate_court_conflict()

	def validate_court_conflict(self):
		"""A Training Session consumes a Court slot - make sure it doesn't
		overlap an existing Facility Booking or Maintenance Schedule on the
		same court/date, and not another Training Session either."""
		if not (self.court and self.date and self.start_time and self.end_time):
			return

		overlap_filters_common = {
			"court": self.court,
			"name": ["!=", self.name],
		}

		# Facility Booking overlap
		booking_conflict = frappe.db.sql(
			"""
			select name from `tabFacility Booking`
			where court = %(court)s
				and booking_date = %(date)s
				and booking_status not in ('Cancelled', 'No-show')
				and (start_time < %(end_time)s and end_time > %(start_time)s)
			limit 1
			""",
			{
				"court": self.court,
				"date": self.date,
				"start_time": self.start_time,
				"end_time": self.end_time,
			},
		)
		if booking_conflict:
			frappe.throw(_("This slot conflicts with an existing Facility Booking on this court."))

		# Maintenance Schedule overlap
		maintenance_conflict = frappe.db.sql(
			"""
			select name from `tabMaintenance Schedule`
			where court = %(court)s
				and scheduled_date = %(date)s
				and status in ('Scheduled', 'In Progress')
				and (scheduled_start < %(end_time)s and scheduled_end > %(start_time)s)
			limit 1
			""",
			{
				"court": self.court,
				"date": self.date,
				"start_time": self.start_time,
				"end_time": self.end_time,
			},
		)
		if maintenance_conflict:
			frappe.throw(_("This slot conflicts with a scheduled Maintenance window on this court."))

		# Other Training Sessions
		session_conflict = frappe.db.sql(
			"""
			select name from `tabTraining Session`
			where court = %(court)s
				and date = %(date)s
				and docstatus != 2
				and name != %(name)s
				and (start_time < %(end_time)s and end_time > %(start_time)s)
			limit 1
			""",
			{
				"court": self.court,
				"date": self.date,
				"start_time": self.start_time,
				"end_time": self.end_time,
				"name": self.name or "",
			},
		)
		if session_conflict:
			frappe.throw(_("This slot conflicts with another Training Session on this court."))

		if len(self.participants or []) > 0 and self.max_participants_limit():
			pass

	def max_participants_limit(self):
		if self.training_schedule:
			max_p = frappe.db.get_value("Training Schedule", self.training_schedule, "max_participants")
			if max_p and len(self.participants or []) > max_p:
				frappe.throw(_("Number of participants exceeds the Training Schedule's max of {0}.").format(max_p))
		return True

	def on_submit(self):
		self.create_session_invoice()

	def create_session_invoice(self):
		"""One invoice per session, billed to the first participant's linked
		Member/Customer for the total of fee_per_participant * headcount.
		If you'd rather bill each participant separately, loop and call
		make_linked_sales_invoice per participant instead."""
		if not self.fee_per_participant or not self.participants:
			return

		# Try to find a billable customer: prefer the first participant's Member
		customer = None
		for row in self.participants:
			member = frappe.db.get_value("Player Registration", row.player, "member")
			customer = get_member_customer(member)
			if customer:
				break

		if not customer:
			frappe.msgprint(
				_("No linked Customer found for participants - skipping invoice creation."),
				alert=True,
			)
			return

		total = self.fee_per_participant * len(self.participants)
		si = make_linked_sales_invoice(
			customer=customer,
			item_code="Training Session Fee",
			item_group="Coaching",
			amount=total,
			link_fieldname="training_session",
			link_docname=self.name,
			description=f"Training Session {self.name} ({len(self.participants)} participant(s))",
		)
		self.db_set("sales_invoice", si.name)
