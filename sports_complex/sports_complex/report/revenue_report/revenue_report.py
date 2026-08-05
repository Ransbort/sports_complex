# Copyright (c) 2026, Sports Complex and contributors
# For license information, please see license.txt

import frappe
from frappe import _


def execute(filters=None):
	filters = filters or {}
	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_columns():
	return [
		{"label": _("Sales Invoice"), "fieldname": "name", "fieldtype": "Link", "options": "Sales Invoice", "width": 140},
		{"label": _("Posting Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 100},
		{"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 160},
		{"label": _("Source"), "fieldname": "source", "fieldtype": "Data", "width": 140},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 90},
		{"label": _("Grand Total"), "fieldname": "grand_total", "fieldtype": "Currency", "width": 120},
	]


def get_data(filters):
	# Sales Invoice is shared across ex_healthcare, retail-suite, and
	# sports_complex - this report must only ever return rows that actually
	# originated from Sports Complex (i.e. carry one of the back-link fields
	# invoicing.py stamps). Without this, every downstream consumer of this
	# report - including any Dashboard Chart built on top of it - silently
	# includes the other apps' revenue too.
	conditions = [
		"si.docstatus = 1",
		"""(
			si.facility_booking is not null
			or si.membership is not null
			or si.membership_renewal is not null
			or si.tournament_registration is not null
			or si.training_session is not null
			or si.equipment_issue is not null
			or si.equipment_return is not null
		)""",
	]
	values = {}

	if filters.get("from_date"):
		conditions.append("si.posting_date >= %(from_date)s")
		values["from_date"] = filters["from_date"]
	if filters.get("to_date"):
		conditions.append("si.posting_date <= %(to_date)s")
		values["to_date"] = filters["to_date"]

	where_clause = " and ".join(conditions)

	rows = frappe.db.sql(
		f"""
		select
			si.name, si.posting_date, si.customer, si.status, si.grand_total,
			si.facility_booking, si.membership, si.membership_renewal,
			si.tournament_registration, si.training_session,
			si.equipment_issue, si.equipment_return
		from `tabSales Invoice` si
		where {where_clause}
		order by si.posting_date desc
		""",
		values,
		as_dict=True,
	)

	for row in rows:
		row["source"] = classify_source(row)

	return rows


def classify_source(row):
	mapping = [
		("facility_booking", _("Facility Booking")),
		("membership", _("Membership")),
		("membership_renewal", _("Membership Renewal")),
		("tournament_registration", _("Tournament")),
		("training_session", _("Coaching")),
		("equipment_issue", _("Equipment Rental")),
		("equipment_return", _("Equipment Damage")),
	]
	for fieldname, label in mapping:
		if row.get(fieldname):
			return label
	return _("Other")