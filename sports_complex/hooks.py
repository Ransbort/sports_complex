app_name = "sports_complex"
app_title = "Sports Complex"
app_publisher = "Ransbort"
app_description = "Sports Complex Management: facilities, bookings, membership, coaching, tournaments, POS, and Paystack payments"
app_email = "ransbort@outlook.com"
app_license = "mit"
required_apps = ["frappe", "healthcare"]
app_home = "/desk/healthcare"

add_to_apps_screen = [
	{
		"name": app_name,
		"logo": "/assets/sports_complex/images/sports_complex.svg",
		"title": app_title,
		"route": app_home,
		"has_permission": "erpnext.check_app_permission",
	}
]

# Includes in <head>
# ------------------
# app_include_css = "/assets/sports_complex/css/sports_complex.css"
# app_include_js = "/assets/sports_complex/js/sports_complex.js"

# Installation
# ------------
after_install = "sports_complex.install.after_install"
after_migrate = "sports_complex.install.after_migrate"
before_uninstall = "sports_complex.uninstall.before_uninstall"

# Document Events
# ---------------
doc_events = {
    "Sales Invoice": {
        # frappe_paystack fires its own payment-confirmed handler; we
        # additionally listen here to flow payment status back onto
        # whichever source doc created the invoice (Facility Booking,
        # Membership, Tournament Registration, Training Session,
        # Equipment Issue/Return — see utils/paystack_hooks.py).
        # NOTE: confirm this is the exact hook name your frappe_paystack
        # fork calls — some forks fire a custom event or expect you to
        # hook `on_update` instead.
        "on_payment_authorized": "sports_complex.sports_complex.utils.paystack_hooks.on_payment_authorized",
    },
    # Medical-first Trials & Player Registration flow — see
    # healthcare_integration.py's module docstring for the full picture.
    # A person enters the pipeline the moment a Patient Appointment with
    # Appointment Type "Trialist" is created (Front Desk check-in, walk-in
    # or pre-booked — no separate entry point needed); the doctor's
    # verdict is recorded via the same "Trialist" Appointment Type
    # inherited onto the resulting Patient Encounter.
    "Patient Appointment": {
        "after_insert": "sports_complex.sports_complex.healthcare_integration.on_patient_appointment_after_insert",
    },
    "Patient Encounter": {
        # Runs once, at creation, before "validate" - copies the Patient's
        # existing Allergies/Medication onto the encounter's own
        # known_allergies/current_medications fields so the doctor isn't
        # retyping them (see healthcare_integration.
        # sync_trial_medical_history_from_patient()). Deliberately not a
        # live/ongoing sync - a later edit here or on the Patient record
        # doesn't flow either way afterwards.
        "before_insert": "sports_complex.sports_complex.healthcare_integration.sync_trial_medical_history_from_patient",
        "validate": "sports_complex.sports_complex.healthcare_integration.validate_patient_encounter",
        "on_submit": "sports_complex.sports_complex.healthcare_integration.on_patient_encounter_submit",
    },
}

# Scheduled Tasks
# ---------------
# scheduler_events = {
#     "daily": [
#         "sports_complex.sports_complex.doctype.maintenance_schedule.maintenance_schedule.mark_overdue",
#     ],
# }

# Fixtures
# --------
fixtures = [
    {
        "dt": "Custom Field",
        "filters": [
            ["dt", "=", "Sales Invoice"],
            [
                "fieldname",
                "in",
                [
                    "sc_source_section",
                    "facility_booking",
                    "membership",
                    "membership_renewal",
                    "column_break_sc_source",
                    "tournament_registration",
                    "training_session",
                    "equipment_issue",
                    "equipment_return",
                ],
            ],
        ],
    },
]
