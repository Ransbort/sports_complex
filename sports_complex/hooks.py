app_name = "sports_complex"
app_title = "Sports Complex"
app_publisher = "Your Company"
app_description = "Sports Complex Management: facilities, bookings, membership, coaching, tournaments, POS, and Paystack payments"
app_email = "you@example.com"
app_license = "mit"
required_apps = ["frappe", "erpnext", "frappe_paystack"]

# Includes in <head>
# ------------------
# app_include_css = "/assets/sports_complex/css/sports_complex.css"
# app_include_js = "/assets/sports_complex/js/sports_complex.js"

# Document Events
# ---------------
# Hook on document methods and events.
#
# NOTE: As later modules (Booking Management, Membership, Events & Tournaments)
# are scaffolded, each one that needs to create a Sales Invoice on submit and
# then get paid via frappe_paystack will register itself here, e.g.:
#
# doc_events = {
#     "Facility Booking": {
#         "on_submit": "sports_complex.sports_complex.doctype.facility_booking.facility_booking.make_sales_invoice",
#     },
#     "Sales Invoice": {
#         # frappe_paystack calls its own payment-confirmed handler; we additionally
#         # listen here to flow payment status back onto the source business doc.
#         "on_payment_authorized": "sports_complex.sports_complex.utils.paystack_hooks.on_payment_authorized",
#     },
# }
doc_events = {}

# Scheduled Tasks
# ---------------
# scheduler_events = {
#     "daily": [
#         "sports_complex.sports_complex.doctype.maintenance_schedule.maintenance_schedule.mark_overdue",
#     ],
# }

# Fixtures
# --------
# fixtures = []
