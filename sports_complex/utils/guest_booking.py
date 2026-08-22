# Copyright (c) 2026, Your Company and contributors
# For license information, please see license.txt

"""Email-OTP verification and Member/Customer resolution for guest
(not-logged-in) court booking - see facility_booking.py's
create_guest_booking() and BOOKING_RECOMMENDATIONS.md.

Member has no linked User today, so there's no login-based identity to
check a guest against. This verifies an emailed one-time code instead
(same shape as the buzz app's guest-booking OTP flow), backed by
frappe.cache() rather than a dedicated doctype since the code is
short-lived, single-use, and not worth persisting.
"""

import hashlib
import hmac
import random
import time

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils.password import get_encryption_key

OTP_CACHE_PREFIX = "sc_booking_otp"
OTP_TTL_SECONDS = 10 * 60

# "Remember this device" for the My Bookings page: after a guest proves
# email ownership once via OTP, list_my_bookings() (facility_booking.py)
# hands back a signed, self-contained token - email + expiry, HMAC'd with
# the site's own encryption key, same construction facility_booking.
# get_booking_access_token() uses for per-booking access links - that the
# browser stores and replays instead of requesting a fresh OTP every
# visit. Stateless by design (no server-side storage or revocation list),
# same trust model as those per-booking tokens, just for the coarser
# "which email is this" identity check this page needs instead of "which
# booking".
REMEMBER_TOKEN_TTL_SECONDS = 30 * 24 * 60 * 60  # 30 days


def _otp_cache_key(email):
	return f"{OTP_CACHE_PREFIX}:{email.strip().lower()}"


# nosemgrep: frappe-semgrep-rules.rules.security.guest-whitelisted-method --
# sending a code to an email address is the entry point of the flow this
# is meant to gate; rate-limited below to bound abuse (email bombing /
# enumeration).
@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(key="email", limit=5, seconds=3600)
def send_booking_otp(email):
	"""Email a 6-digit one-time code to verify a guest's email before
	letting them book without an account.
	"""
	email = (email or "").strip().lower()
	if not email or "@" not in email:
		frappe.throw(_("Enter a valid email address"))

	otp = f"{random.randint(0, 999999):06d}"
	frappe.cache().set_value(_otp_cache_key(email), otp, expires_in_sec=OTP_TTL_SECONDS)

	frappe.sendmail(
		recipients=[email],
		subject=_("Your court booking verification code"),
		message=_("Your verification code is {0}. It expires in 10 minutes.").format(
			f"<b style='font-size: 1.25em; letter-spacing: 0.15em;'>{otp}</b>"
		),
		now=True,
	)
	return {"sent": True}


def verify_booking_otp(email, otp):
	"""Raises if the code is missing, wrong, or expired. Deletes the
	cached code on success so it can't be replayed for a second booking.
	"""
	email = (email or "").strip().lower()
	cached = frappe.cache().get_value(_otp_cache_key(email))
	if not cached or not otp or str(otp).strip() != cached:
		frappe.throw(_("Invalid or expired verification code"))
	frappe.cache().delete_value(_otp_cache_key(email))


def _remember_token_signature(email, expires_at):
	key = get_encryption_key().encode()
	msg = f"{email.strip().lower()}:{expires_at}".encode()
	return hmac.new(key, msg, hashlib.sha256).hexdigest()


def issue_my_bookings_remember_token(email):
	"""A fresh token good for REMEMBER_TOKEN_TTL_SECONDS from now. Called
	every time list_my_bookings() re-establishes a guest's identity -
	whether via a fresh OTP or an already-valid remember token - so
	returning within the window keeps sliding it forward, rather than the
	guest getting logged out exactly 30 days after the one time they
	typed a code.
	"""
	email = (email or "").strip().lower()
	expires_at = int(time.time()) + REMEMBER_TOKEN_TTL_SECONDS
	return f"{expires_at}.{_remember_token_signature(email, expires_at)}"


def verify_my_bookings_remember_token(email, token):
	"""True if token is a valid, unexpired remember-token for this email.
	Never raises - a missing/malformed/expired/tampered token should just
	fall back to asking for a fresh OTP, not surface as an error for
	something the guest didn't do this visit.
	"""
	email = (email or "").strip().lower()
	if not email or not token:
		return False
	try:
		expires_at_str, signature = token.split(".", 1)
		expires_at = int(expires_at_str)
	except (ValueError, AttributeError):
		return False
	if expires_at < int(time.time()):
		return False
	return hmac.compare_digest(_remember_token_signature(email, expires_at), signature)


def resolve_or_create_guest_customer(email, full_name, phone=None):
	"""Find-or-create a Member (which auto-creates its own linked
	Customer - see Member.before_insert/create_customer) for a guest who
	has just verified their email. Reuses whatever Member already exists
	for this email rather than creating a duplicate every time the same
	guest books again.
	"""
	email = (email or "").strip().lower()
	existing_customer = frappe.db.get_value("Member", {"email": email}, "customer")
	if existing_customer:
		return existing_customer

	full_name = (full_name or "").strip()
	if not full_name:
		frappe.throw(_("Full name is required"))

	# ignore_permissions on the Member/Customer docs we create directly
	# doesn't reach whatever Contact record ERPNext's own Customer
	# controller creates/updates as a side effect of that insert (since
	# we set email/phone on the Customer) - that's a separate Document
	# instance, constructed deep inside code we don't control, that
	# never gets our ignore_permissions flag (confirmed: setting
	# frappe.flags.ignore_permissions globally around this block still
	# hit "No permission for Contact" for the Guest role). Running this
	# whole nested chain as Administrator - who always has full access
	# by Frappe's design, independent of any doctype's role permissions
	# - covers it regardless of which nested doc needs the bypass,
	# rather than us having to keep discovering them one at a time.
	# Restored to the real (Guest) session user immediately after, in a
	# finally so it can't leak into the rest of the request even if
	# member.insert() raises.
	original_user = frappe.session.user
	frappe.set_user("Administrator")
	try:
		member = frappe.new_doc("Member")
		member.member_name = full_name
		member.email = email
		if phone:
			member.phone = phone
		member.insert(ignore_permissions=True)
	finally:
		frappe.set_user(original_user)

	return member.customer
