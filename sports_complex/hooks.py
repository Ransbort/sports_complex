app_name = "sports_complex"
app_title = "Sports Complex"
app_publisher = "Ransbort"
app_description = "Sports Complex Management: facilities, bookings, membership, coaching, tournaments, POS, and Paystack payments"
app_email = "ransbort@outlook.com"
app_license = "mit"
required_apps = ["frappe"]

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
    # Medical-clearance flow for the Trials & Player Registration module —
    # see healthcare_integration.py. validate blocks submitting a trial
    # medical encounter with no Fitness Result recorded; on_submit
    # propagates the doctor's verdict back onto the linked Trialist.
    "Patient Encounter": {
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
