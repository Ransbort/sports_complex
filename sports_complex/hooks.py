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
        # Kept as a fallback in case a future Payment Entry-based flow (or
        # a different frappe_paystack fork) fires it, but this event isn't
        # actually raised by the frappe_paystack integration this app uses
        # today — see utils/paystack_hooks.py's module docstring. This
        # used to point at a `utils` package that didn't exist anywhere in
        # the app; Facility Booking's Payment Pending -> Confirmed flow
        # now genuinely runs off the hook below instead.
        "on_payment_authorized": "sports_complex.sports_complex.utils.paystack_hooks.on_payment_authorized",
    },
    "Paystack Payment Log": {
        # The hook that actually fires: frappe_paystack's verify_transaction()
        # (checkout page's synchronous fallback) and its webhook handler
        # both just save() this doctype once a payment settles. Flows
        # payment status back onto Facility Booking today — see
        # utils/paystack_hooks.py and FacilityBooking.mark_paid_and_confirm().
        "on_update": "sports_complex.sports_complex.utils.paystack_hooks.on_payment_log_update",
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
        # sync_trial_medical_history_from_patient()), and separately
        # populates the standard Lab Tests section with this trial's
        # already-completed predetermined lab panel (see
        # healthcare_integration.attach_trial_lab_results_to_encounter() -
        # "Lab stage" section of that module's docstring). Both are
        # deliberately one-time, at-creation copies, not a live/ongoing
        # sync - a later edit here or on the source record doesn't flow
        # either way afterwards.
        "before_insert": [
            "sports_complex.sports_complex.healthcare_integration.sync_trial_medical_history_from_patient",
            "sports_complex.sports_complex.healthcare_integration.attach_trial_lab_results_to_encounter",
        ],
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
