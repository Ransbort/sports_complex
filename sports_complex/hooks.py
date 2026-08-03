app_name = "sports_complex"
app_title = "Sports Complex"
app_publisher = "Ransford Borketey"
app_description = "sports management app built on frappe"
app_email = "ransbort@outlook.com"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "sports_complex",
# 		"logo": "/assets/sports_complex/logo.png",
# 		"title": "Sports Complex",
# 		"route": "/sports_complex",
# 		"has_permission": "sports_complex.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/sports_complex/css/sports_complex.css"
# app_include_js = "/assets/sports_complex/js/sports_complex.js"

# include js, css files in header of web template
# web_include_css = "/assets/sports_complex/css/sports_complex.css"
# web_include_js = "/assets/sports_complex/js/sports_complex.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "sports_complex/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "sports_complex/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "sports_complex.utils.jinja_methods",
# 	"filters": "sports_complex.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "sports_complex.install.before_install"
# after_install = "sports_complex.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "sports_complex.uninstall.before_uninstall"
# after_uninstall = "sports_complex.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "sports_complex.utils.before_app_install"
# after_app_install = "sports_complex.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "sports_complex.utils.before_app_uninstall"
# after_app_uninstall = "sports_complex.utils.after_app_uninstall"

# Build
# ------------------
# To hook into the build process

# after_build = "sports_complex.build.after_build"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "sports_complex.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"sports_complex.tasks.all"
# 	],
# 	"daily": [
# 		"sports_complex.tasks.daily"
# 	],
# 	"hourly": [
# 		"sports_complex.tasks.hourly"
# 	],
# 	"weekly": [
# 		"sports_complex.tasks.weekly"
# 	],
# 	"monthly": [
# 		"sports_complex.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "sports_complex.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "sports_complex.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "sports_complex.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "sports_complex.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["sports_complex.utils.before_request"]
# after_request = ["sports_complex.utils.after_request"]

# Job Events
# ----------
# before_job = ["sports_complex.utils.before_job"]
# after_job = ["sports_complex.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"sports_complex.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []

