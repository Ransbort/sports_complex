const { createApp } = Vue;

const STATUS_BADGE_CLASS = {
  Draft: 'bk-badge-grey',
  'Payment Pending': 'bk-badge-yellow',
  Confirmed: 'bk-badge-blue',
  'Checked-In': 'bk-badge-yellow',
  Completed: 'bk-badge-total',
  Cancelled: 'bk-badge-red',
  'No-show': 'bk-badge-red',
};

// "Remember this device" so a guest who already verified an email here
// doesn't have to request and retype a fresh code every visit - see
// issue_my_bookings_remember_token()/verify_my_bookings_remember_token()
// in sports_complex/utils/guest_booking.py for the signed-token side of
// this. Stored in localStorage (not a cookie - nothing server-side needs
// to read it) under a versioned key so a future format change can't be
// misread as a valid-looking but stale token.
const REMEMBER_KEY = 'sc_my_bookings_remember_v1';

// frappe.call() already pops its own "Message" dialog for any server-side
// frappe.throw() before the call's promise even rejects - showing our own
// generic Swal on top of that every time was a second, less specific
// dialog stacked over whatever the server actually said. Skip our own
// fallback whenever the server already explained itself, and keep it only
// for genuinely unexpected failures (network errors, etc.) that have
// nothing else on screen to explain them.
//
// The reject value .catch() hands back is the raw jqXHR, not the parsed
// response body - frappe.request.cleanup() parses xhr.responseText into
// its own local object (that's what powers the automatic "Message" popup)
// but never copies _server_messages back onto the xhr object itself, so a
// bare `err._server_messages` check was always undefined and this
// fallback fired on every server error regardless. The real field lives
// at err.responseJSON._server_messages (jQuery parses a JSON response
// body onto .responseJSON automatically) - checking both here covers that
// and any future frappe version that does put it on err directly.
function hasServerMessage(err) {
  if (!err) return false;
  if (err._server_messages) return true;
  if (err.responseJSON && err.responseJSON._server_messages) return true;
  return false;
}

function loadRememberedIdentity() {
  try {
    const raw = localStorage.getItem(REMEMBER_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (parsed && parsed.email && parsed.token) return parsed;
  } catch (e) {
    // Storage unavailable (private browsing, disabled, corrupt value) -
    // just fall back to the normal email/OTP form.
  }
  return null;
}

createApp({
  delimiters: ['[[', ']]'],
  data() {
    // Read synchronously so the template can skip straight to a loading
    // spinner instead of flashing the email form first (see
    // checkingRemembered below and its use in the template).
    const remembered = loadRememberedIdentity();
    return {
      isGuest: !!window.isGuest,
      guestEmail: (remembered && remembered.email) || '',
      guestOtp: '',
      otpSent: false,
      sendingOtp: false,
      otpCountdown: 0,
      otpCountdownTimer: null,
      verified: false,
      // True only while a remembered identity is being checked in the
      // background on page load - see mounted()/tryRememberedLogin().
      checkingRemembered: !!(window.isGuest && remembered),
      rememberedToken: remembered ? remembered.token : null,
      loading: false,
      loaded: false,
      bookings: [],
      filterStatus: '',
      filterFacility: '',
      filterSearch: '',
      currentPage: 1,
      pageSize: 10,
    };
  },
  computed: {
    canSendOtp() {
      return /\S+@\S+\.\S+/.test(this.guestEmail);
    },
    // Drives the v-if in the template: the narrow identity-gate card shows
    // only while we actually need an email/OTP from a guest. A logged-in
    // customer, or a guest whose remembered token already checked out (or
    // is still being checked - see checkingRemembered), goes straight to
    // the full-screen table instead.
    showAuthGate() {
      return this.isGuest && !this.verified;
    },
    statusOptions() {
      const seen = new Set(this.bookings.map(b => b.booking_status).filter(Boolean));
      return Array.from(seen).sort();
    },
    facilityOptions() {
      const seen = new Set(this.bookings.map(b => b.facility_name).filter(Boolean));
      return Array.from(seen).sort();
    },
    filteredBookings() {
      const search = this.filterSearch.trim().toLowerCase();
      return this.bookings.filter(b => {
        if (this.filterStatus && b.booking_status !== this.filterStatus) return false;
        if (this.filterFacility && b.facility_name !== this.filterFacility) return false;
        if (search && !(b.facility_name || '').toLowerCase().includes(search)) return false;
        return true;
      });
    },
    hasActiveFilters() {
      return !!(this.filterStatus || this.filterFacility || this.filterSearch);
    },
    totalPages() {
      return Math.max(1, Math.ceil(this.filteredBookings.length / this.pageSize));
    },
    // currentPage can end up past the last page after a filter shrinks the
    // result set (see the watcher below, which resets it eagerly) or after
    // bookings reload - clamping here as well means the table never tries
    // to render a page that doesn't exist, even for a moment.
    pagedBookings() {
      const page = Math.min(this.currentPage, this.totalPages);
      const start = (page - 1) * this.pageSize;
      return this.filteredBookings.slice(start, start + this.pageSize);
    },
    pageRangeStart() {
      return this.filteredBookings.length ? (Math.min(this.currentPage, this.totalPages) - 1) * this.pageSize + 1 : 0;
    },
    pageRangeEnd() {
      return Math.min(this.pageRangeStart + this.pageSize - 1, this.filteredBookings.length);
    },
  },
  watch: {
    // A filter change can shrink filteredBookings enough that the page the
    // user was on no longer exists - jump back to page 1 rather than
    // showing an empty page with real results one page back.
    filterStatus() { this.currentPage = 1; },
    filterFacility() { this.currentPage = 1; },
    filterSearch() { this.currentPage = 1; },
  },
  mounted() {
    // A logged-in customer's identity comes from their session - no email/
    // OTP step needed, so load straight away. A guest with a remembered,
    // not-yet-expired identity skips straight to loading too. Otherwise a
    // guest sees the identity form instead (see the v-if in the template)
    // and loads only after verifying their code.
    if (!this.isGuest) {
      this.loadBookings();
    } else if (this.checkingRemembered) {
      this.tryRememberedLogin();
    }
  },
  methods: {
    fmt(amount) {
      return Number(amount || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    },
    statusClass(status) {
      return STATUS_BADGE_CLASS[status] || 'bk-badge-grey';
    },
    bookingUrl(b) {
      const token = b.token ? `?token=${encodeURIComponent(b.token)}` : '';
      return `/booking-confirmation/${b.name}${token}`;
    },
    directionsUrl(b) {
      // Same fallback order as booking-confirmation's own directionsUrl:
      // prefer the venue's geocoded pin, fall back to an address/city text
      // query when a venue hasn't been located on the map yet.
      if (b.venue_lat != null && b.venue_lon != null) {
        return `https://www.google.com/maps/dir/?api=1&destination=${b.venue_lat},${b.venue_lon}`;
      }
      const query = [b.venue_address, b.venue_city].filter(Boolean).join(', ');
      return query ? `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(query)}` : null;
    },
    sendOtp() {
      this.sendingOtp = true;
      frappe.call(
        'sports_complex.utils.guest_booking.send_booking_otp',
        { email: this.guestEmail }
      ).then(() => {
        this.otpSent = true;
        this.sendingOtp = false;
        this.startOtpCountdown();
      }).catch((err) => {
        if (!hasServerMessage(err)) {
          Swal.fire('Error', 'Could not send the verification code. Please check the email address and try again.', 'error');
        }
        this.sendingOtp = false;
      });
    },
    resendOtp() {
      // Guarded on the same otpCountdown the button itself is hidden
      // behind, so this can't fire before the countdown from the last
      // send has actually run out.
      if (this.otpCountdown > 0 || this.sendingOtp) return;
      this.guestOtp = '';
      this.sendingOtp = true;
      frappe.call(
        'sports_complex.utils.guest_booking.send_booking_otp',
        { email: this.guestEmail }
      ).then(() => {
        this.sendingOtp = false;
        this.startOtpCountdown();
      }).catch((err) => {
        if (!hasServerMessage(err)) {
          Swal.fire('Error', 'Could not resend the verification code. Please try again.', 'error');
        }
        this.sendingOtp = false;
      });
    },
    startOtpCountdown(seconds = 30) {
      this.otpCountdown = seconds;
      if (this.otpCountdownTimer) clearInterval(this.otpCountdownTimer);
      this.otpCountdownTimer = setInterval(() => {
        this.otpCountdown -= 1;
        if (this.otpCountdown <= 0) {
          clearInterval(this.otpCountdownTimer);
          this.otpCountdownTimer = null;
          this.otpCountdown = 0;
        }
      }, 1000);
    },
    verifyAndLoad() {
      this.loading = true;
      frappe.call(
        'sports_complex.sports_complex.doctype.facility_booking.facility_booking.list_my_bookings',
        { email: this.guestEmail, otp: this.guestOtp }
      ).then(r => {
        this.bookings = (r.message && r.message.bookings) || [];
        this.rememberIdentity(this.guestEmail, r.message && r.message.remember_token);
        this.verified = true;
        this.loaded = true;
        this.loading = false;
      }).catch((err) => {
        if (!hasServerMessage(err)) {
          Swal.fire('Error', 'Invalid or expired code. Please try again.', 'error');
        }
        this.loading = false;
      });
    },
    loadBookings() {
      this.loading = true;
      frappe.call(
        'sports_complex.sports_complex.doctype.facility_booking.facility_booking.list_my_bookings',
        {}
      ).then(r => {
        this.bookings = (r.message && r.message.bookings) || [];
        this.loaded = true;
        this.loading = false;
      }).catch((err) => {
        if (!hasServerMessage(err)) {
          Swal.fire('Error', 'Could not load your bookings.', 'error');
        }
        this.loading = false;
      });
    },
    tryRememberedLogin() {
      this.loading = true;
      frappe.call(
        'sports_complex.sports_complex.doctype.facility_booking.facility_booking.list_my_bookings',
        { email: this.guestEmail, remember_token: this.rememberedToken }
      ).then(r => {
        // A stale/tampered token comes back as {verified: false} instead
        // of a rejected call (see list_my_bookings()'s docstring) - this
        // was an automatic convenience check, not something the guest did
        // this visit, so it falls back to the normal email/OTP form
        // silently rather than surfacing as an error.
        if (!r.message || !r.message.verified) {
          this.forgetIdentity();
          this.checkingRemembered = false;
          this.loading = false;
          return;
        }
        this.bookings = r.message.bookings || [];
        this.rememberIdentity(this.guestEmail, r.message.remember_token);
        this.verified = true;
        this.loaded = true;
        this.loading = false;
        this.checkingRemembered = false;
      }).catch(() => {
        // Genuinely unexpected failure (network error, etc.) rather than
        // an invalid token - same silent fallback either way.
        this.forgetIdentity();
        this.checkingRemembered = false;
        this.loading = false;
      });
    },
    rememberIdentity(email, token) {
      this.rememberedToken = token || null;
      try {
        if (token) {
          localStorage.setItem(REMEMBER_KEY, JSON.stringify({ email, token }));
        }
      } catch (e) {
        // Storage unavailable - the convenience just doesn't persist;
        // everything else on the page still works normally.
      }
    },
    forgetIdentity() {
      this.rememberedToken = null;
      try {
        localStorage.removeItem(REMEMBER_KEY);
      } catch (e) {
        // ignore
      }
    },
    clearFilters() {
      this.filterStatus = '';
      this.filterFacility = '';
      this.filterSearch = '';
      // The filterStatus/filterFacility/filterSearch watchers above already
      // reset currentPage when each fires, but setting it here too keeps
      // this method correct on its own even if that wiring ever changes.
      this.currentPage = 1;
    },
    prevPage() {
      if (this.currentPage > 1) this.currentPage -= 1;
    },
    nextPage() {
      if (this.currentPage < this.totalPages) this.currentPage += 1;
    },
    reset() {
      this.verified = false;
      this.otpSent = false;
      this.guestOtp = '';
      // "Check a different email" - clear the prefilled address too
      // (it may only be there because a remembered identity filled it
      // in), and forget any remembered identity so it doesn't just
      // silently reload on the next visit.
      this.guestEmail = '';
      this.loaded = false;
      this.bookings = [];
      this.otpCountdown = 0;
      // Stale filters (and pagination) from the last identity shouldn't
      // silently carry over to whoever's bookings load next.
      this.clearFilters();
      this.forgetIdentity();
      if (this.otpCountdownTimer) {
        clearInterval(this.otpCountdownTimer);
        this.otpCountdownTimer = null;
      }
    },
  },
  beforeUnmount() {
    if (this.otpCountdownTimer) clearInterval(this.otpCountdownTimer);
  },
}).mount('#app');
