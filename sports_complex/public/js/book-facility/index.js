const { createApp } = Vue;

// frappe.call() already pops its own "Message" dialog for any server-side
// frappe.throw() (it renders _server_messages before the call's promise
// even rejects) - showing our own generic Swal on top of that every time
// was a second, less specific dialog stacked over the real reason (e.g.
// "Bookings must be made at least 1.0 hour(s) before the start time" was
// buried behind "Could not create the booking(s)... please try again").
// Skip our own fallback whenever the server already explained itself, and
// keep it only for genuinely unexpected failures (network errors, etc.)
// that have nothing else on screen to explain them.
//
// The reject value frappe.call()'s .catch() hands back is the raw jqXHR,
// not the parsed response body - frappe.request.cleanup() parses
// xhr.responseText into its own local object (that's what powers the
// automatic "Message" popup) but never copies _server_messages back onto
// the xhr object itself, so a bare `err._server_messages` check is always
// undefined and this fallback fired on every single server error
// regardless. The real field lives at err.responseJSON._server_messages
// (jQuery parses a JSON response body onto .responseJSON automatically) -
// checking both here covers that and any future frappe version that does
// put it on err directly.
function hasServerMessage(err) {
  if (!err) return false;
  if (err._server_messages) return true;
  if (err.responseJSON && err.responseJSON._server_messages) return true;
  return false;
}

// "Remember this browser" for a short window after a guest verifies their
// email - see BOOKING_REMEMBER_TOKEN_TTL_SECONDS / issue_booking_remember_
// token() / verify_booking_remember_token() in sports_complex/utils/
// guest_booking.py. A guest who already typed a correct code once doesn't
// have to fetch and retype another one for a second booking in the same
// sitting (or a page reload within the window) - create_guest_booking_
// cart() accepts this token in place of otp and hands back a fresh one
// covering the same window from now on every success, sliding it forward.
// Stored in localStorage under a versioned key, same pattern (and same
// "never surface a stale/tampered token as an error" philosophy) as my-
// bookings' own REMEMBER_KEY - but a completely separate key and a
// separate signed-token construction server-side, so the two can never be
// used interchangeably.
const REMEMBER_KEY = 'sc_booking_remember_v1';

function loadRememberedBooking() {
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

function saveRememberedBooking(email, token) {
  try {
    localStorage.setItem(REMEMBER_KEY, JSON.stringify({ email: (email || '').trim().toLowerCase(), token }));
  } catch (e) {
    // Storage unavailable - the guest just won't be remembered next visit.
  }
}

function clearRememberedBooking() {
  try {
    localStorage.removeItem(REMEMBER_KEY);
  } catch (e) {
    // Nothing to do if storage isn't available in the first place.
  }
}

createApp({
  delimiters: ['[[', ']]'],
  data() {
    const now = new Date();
    const today = now.toISOString().slice(0, 10);
    // Read synchronously so a returning guest's email is already filled in
    // (and the verified state already known) by the time the details step
    // first renders, rather than flashing the normal form first.
    const remembered = loadRememberedBooking();
    return {
      facilities: window.facilities || [],
      isGuest: !!window.isGuest,
      step: 'grid', // 'grid' -> 'browse' -> 'details' -> 'result'
      today,
      selectedFacility: '',
      selectedDate: today,
      dowLabels: ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'],
      visibleYear: now.getFullYear(),
      visibleMonth: now.getMonth() + 1, // 1-12
      monthAvailability: {},
      loadingMonth: false,
      loadingSlots: false,
      slotsChecked: false,
      slots: [],
      // Selected slots across this facility-browsing session - can span
      // several dates (pick a day, add some slots, pick another day, add
      // more) before checking out together. Each item is
      // { booking_date, start_time, end_time }.
      cart: [],
      notes: '',
      guestName: '',
      guestEmail: (remembered && remembered.email) || '',
      guestPhone: '',
      guestOtp: '',
      otpSent: false,
      sendingOtp: false,
      otpCountdown: 0,
      otpCountdownTimer: null,
      // The email a still-unexpired remember-token was actually issued for
      // - kept separate from guestEmail (which the guest can keep typing
      // into) so guestVerified only reads true while the two still match.
      guestRememberEmail: (remembered && remembered.email) || '',
      guestRememberToken: remembered ? remembered.token : null,
      booking: false,
      result: null,
      paymentPopup: null,
      paymentPollTimer: null,
    };
  },
  computed: {
    canSendOtp() {
      return this.guestName.trim() && /\S+@\S+\.\S+/.test(this.guestEmail);
    },
    // True while a remember-token exists, hasn't passed its own embedded
    // expiry (read straight off the token - see issue_booking_remember_
    // token(), which prefixes it with the plaintext unix timestamp so the
    // client can check this without a round trip), and was issued for
    // exactly the email currently typed in. The server re-checks this for
    // real (including the signature) when the booking is actually
    // submitted - this only decides whether to show the OTP step at all.
    guestVerified() {
      if (!this.guestRememberToken || !this.guestRememberEmail) return false;
      if (this.guestRememberEmail !== this.guestEmail.trim().toLowerCase()) return false;
      const expiresAt = parseInt(this.guestRememberToken.split('.')[0], 10);
      return Number.isFinite(expiresAt) && expiresAt * 1000 > Date.now();
    },
    detailsSubmitLabel() {
      if (this.guestVerified) return this.booking ? 'Booking…' : 'Confirm Booking';
      return this.sendingOtp ? 'Sending…' : 'Send Verification Code';
    },
    detailsSubmitDisabled() {
      if (this.guestVerified) return this.booking || !this.cart.length;
      return !this.canSendOtp || this.sendingOtp;
    },
    selectedFacilityInfo() {
      return this.facilities.find(f => f.name === this.selectedFacility) || {};
    },
    cartTotal() {
      const rate = Number(this.selectedFacilityInfo.hourly_rate || 0);
      return this.cart.reduce((sum, item) => sum + rate * this.slotHours(item), 0);
    },
    daysInMonth() {
      const count = new Date(this.visibleYear, this.visibleMonth, 0).getDate();
      return Array.from({ length: count }, (_, i) => i + 1);
    },
    leadingBlanks() {
      const count = new Date(this.visibleYear, this.visibleMonth - 1, 1).getDay();
      return Array.from({ length: count }, (_, i) => i);
    },
    monthLabel() {
      return new Date(this.visibleYear, this.visibleMonth - 1, 1)
        .toLocaleString(undefined, { month: 'long', year: 'numeric' });
    },
    isPrevMonthDisabled() {
      const now = new Date();
      return this.visibleYear === now.getFullYear() && this.visibleMonth === now.getMonth() + 1;
    },
  },
  methods: {
    fmt(amount) {
      return Number(amount || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    },
    pad2(n) {
      return String(n).padStart(2, '0');
    },
    dayKey(day) {
      return `${this.visibleYear}-${this.pad2(this.visibleMonth)}-${this.pad2(day)}`;
    },
    isToday(day) {
      return this.dayKey(day) === this.today;
    },
    isSelected(day) {
      return this.dayKey(day) === this.selectedDate;
    },
    isPastDay(day) {
      return this.dayKey(day) < this.today;
    },
    selectDay(day) {
      if (this.isPastDay(day)) return;
      this.selectedDate = this.dayKey(day);
      this.checkAvailability();
    },
    shiftMonth(delta) {
      let m = this.visibleMonth + delta;
      let y = this.visibleYear;
      if (m < 1) { m = 12; y -= 1; }
      if (m > 12) { m = 1; y += 1; }
      this.visibleMonth = m;
      this.visibleYear = y;
      this.loadMonthAvailability();
    },
    prevMonth() {
      if (this.isPrevMonthDisabled) return;
      this.shiftMonth(-1);
    },
    nextMonth() {
      this.shiftMonth(1);
    },
    loadMonthAvailability() {
      if (!this.selectedFacility) return;
      this.loadingMonth = true;
      // The loading flag is reset in both the success and error branches
      // below (rather than in a trailing .finally()) so the calendar can't
      // get stuck showing "Loading availability..." if the frappe.call
      // promise this site's version returns doesn't support .finally().
      frappe.call(
        'sports_complex.sports_complex.doctype.facility_booking.facility_booking.get_month_availability',
        { sports_facility: this.selectedFacility, year: this.visibleYear, month: this.visibleMonth }
      ).then(r => {
        this.monthAvailability = r.message || {};
        this.loadingMonth = false;
      }).catch(() => {
        // Non-fatal: the calendar still works for picking a day and
        // checking that day's slots directly - just without the dots.
        this.loadingMonth = false;
      });
    },
    pickFacility(facility) {
      this.selectedFacility = facility.name;
      this.cart = [];
      this.step = 'browse';
      const now = new Date();
      this.visibleYear = now.getFullYear();
      this.visibleMonth = now.getMonth() + 1;
      this.monthAvailability = {};
      this.loadMonthAvailability();
      this.checkAvailability();
    },
    backToGrid() {
      // Leaving this facility's browse session entirely - an in-progress
      // cart for it wouldn't mean anything back on the grid, and starting
      // a facility over should start clean rather than carrying over
      // whatever was selected last time.
      this.cart = [];
      this.step = 'grid';
    },
    checkAvailability() {
      this.loadingSlots = true;
      this.slotsChecked = false;
      frappe.call(
        'sports_complex.sports_complex.doctype.facility_booking.facility_booking.get_available_slots',
        { sports_facility: this.selectedFacility, date: this.selectedDate }
      ).then(r => {
        this.slots = r.message || [];
        this.slotsChecked = true;
        this.loadingSlots = false;
      }).catch(() => {
        Swal.fire('Error', 'Could not load availability. Please try again.', 'error');
        this.loadingSlots = false;
      });
    },
    slotHours(item) {
      const toMinutes = t => {
        const [h, m] = t.split(':').map(Number);
        return h * 60 + m;
      };
      return (toMinutes(item.end_time) - toMinutes(item.start_time)) / 60;
    },
    cartIndex(booking_date, start_time, end_time) {
      return this.cart.findIndex(
        item => item.booking_date === booking_date && item.start_time === start_time && item.end_time === end_time
      );
    },
    isSlotSelected(slot) {
      return this.cartIndex(this.selectedDate, slot.start_time, slot.end_time) >= 0;
    },
    toggleSlot(slot) {
      const idx = this.cartIndex(this.selectedDate, slot.start_time, slot.end_time);
      if (idx >= 0) {
        this.cart.splice(idx, 1);
      } else {
        this.cart.push({ booking_date: this.selectedDate, start_time: slot.start_time, end_time: slot.end_time });
      }
    },
    removeFromCart(item) {
      const idx = this.cartIndex(item.booking_date, item.start_time, item.end_time);
      if (idx >= 0) this.cart.splice(idx, 1);
    },
    confirmBooking() {
      this.booking = true;
      frappe.call(
        'sports_complex.sports_complex.doctype.facility_booking.facility_booking.create_booking_cart',
        {
          slots: this.cart.map(item => ({
            sports_facility: this.selectedFacility,
            booking_date: item.booking_date,
            start_time: item.start_time,
            end_time: item.end_time,
          })),
          notes: this.notes,
        }
      ).then(r => {
        this.result = r.message;
        this.cart = [];
        this.notes = '';
        this.step = 'result';
        this.booking = false;
      }).catch((err) => {
        if (!hasServerMessage(err)) {
          Swal.fire('Error', 'Could not create the booking(s). One or more slots may have just been taken - please choose again.', 'error');
        }
        this.booking = false;
      });
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
      // behind, so this can't fire (e.g. a stray Enter keypress) before
      // the countdown from the last send has actually run out.
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
    // Handles the first form's submit: skip straight to booking for an
    // already-verified guest, otherwise send a fresh code as before.
    proceedFromDetails() {
      if (this.guestVerified) {
        this.confirmGuestBooking();
      } else {
        this.sendOtp();
      }
    },
    rememberGuestVerification(email, token) {
      if (!token) return;
      this.guestRememberToken = token;
      this.guestRememberEmail = (email || '').trim().toLowerCase();
      saveRememberedBooking(email, token);
    },
    forgetGuestVerification() {
      this.guestRememberToken = null;
      this.guestRememberEmail = '';
      clearRememberedBooking();
    },
    confirmGuestBooking() {
      // Captured before the call so the .catch() below can tell whether
      // this attempt was riding a remember-token or a freshly-typed code -
      // a remember-token rejection (expired right at the edge, clock skew)
      // should quietly fall back to asking for a new code, not show the
      // same generic error a wrong/expired typed code would.
      const usingRememberToken = this.guestVerified;
      this.booking = true;
      frappe.call(
        'sports_complex.sports_complex.doctype.facility_booking.facility_booking.create_guest_booking_cart',
        {
          slots: this.cart.map(item => ({
            sports_facility: this.selectedFacility,
            booking_date: item.booking_date,
            start_time: item.start_time,
            end_time: item.end_time,
          })),
          email: this.guestEmail,
          otp: this.guestOtp,
          remember_token: this.guestRememberToken,
          full_name: this.guestName,
          phone: this.guestPhone,
          notes: this.notes,
        }
      ).then(r => {
        this.result = r.message;
        this.rememberGuestVerification(this.guestEmail, r.message && r.message.remember_token);
        this.cart = [];
        this.notes = '';
        this.step = 'result';
        this.booking = false;
      }).catch((err) => {
        if (usingRememberToken) {
          this.forgetGuestVerification();
          this.otpSent = false;
          this.guestOtp = '';
          this.booking = false;
          Swal.fire('Verification expired', 'Please verify your email again to continue.', 'info');
          return;
        }
        if (!hasServerMessage(err)) {
          Swal.fire('Error', 'Could not verify the code or create the booking(s). Please try again.', 'error');
        }
        this.booking = false;
      });
    },
    bookingViewUrl(b) {
      const token = b.token ? `?token=${encodeURIComponent(b.token)}` : '';
      return `/booking-confirmation/${b.name}${token}`;
    },
    payNow() {
      // Opened as a named popup (rather than the previous target="_blank"
      // new tab) so the guest never fully leaves this page - we can poll
      // the booking's status while it's open and flip this page over to
      // "Confirmed" the moment Paystack reports payment received, instead
      // of relying on the guest to come back and refresh manually.
      const url = this.result && this.result.payment_link;
      if (!url) return;

      const w = 480;
      const h = 720;
      const left = Math.round(window.screenX + (window.outerWidth - w) / 2);
      const top = Math.round(window.screenY + (window.outerHeight - h) / 2);
      const popup = window.open(
        url,
        'bk_payment',
        `width=${w},height=${h},left=${left},top=${top},resizable=yes,scrollbars=yes`
      );

      if (!popup) {
        // Pop-up blocked by the browser - fall back to a normal same-tab
        // redirect so paying still works, just without the popup UX.
        window.location.href = url;
        return;
      }

      this.paymentPopup = popup;
      this.watchPayment();
    },
    watchPayment() {
      if (this.paymentPollTimer) clearInterval(this.paymentPollTimer);
      this.paymentPollTimer = setInterval(() => {
        const popup = this.paymentPopup;
        if (popup && popup.closed) {
          clearInterval(this.paymentPollTimer);
          this.paymentPollTimer = null;
          this.paymentPopup = null;
          this.refreshPaymentStatus();
          return;
        }
        this.refreshPaymentStatus();
      }, 3000);
    },
    refreshPaymentStatus() {
      // Every booking in a cart is confirmed/paid together (see
      // _finalize_cart_bookings() / paystack_hooks.on_payment_authorized())
      // - checking the first one's status stands in for the whole cart's.
      const primary = this.result && this.result.bookings && this.result.bookings[0];
      if (!primary) return;
      frappe.call(
        'sports_complex.sports_complex.doctype.facility_booking.facility_booking.get_booking_status',
        { facility_booking: primary.name, token: primary.token }
      ).then(r => {
        const status = r.message;
        if (!status) return;
        if (status.booking_status === 'Confirmed' || status.payment_status === 'Paid') {
          this.result.booking_status = status.booking_status;
          this.result.payment_link = null;
          if (this.paymentPollTimer) {
            clearInterval(this.paymentPollTimer);
            this.paymentPollTimer = null;
          }
          if (this.paymentPopup && !this.paymentPopup.closed) {
            this.paymentPopup.close();
          }
          this.paymentPopup = null;
          Swal.fire('Payment received', 'Your booking is confirmed.', 'success');
        }
      }).catch(() => {
        // Non-fatal: the guest can still complete payment in the popup and
        // check status later via "View Booking" - no need to interrupt
        // them with an error over a background status check.
      });
    },
  },
  beforeUnmount() {
    if (this.paymentPollTimer) clearInterval(this.paymentPollTimer);
    if (this.otpCountdownTimer) clearInterval(this.otpCountdownTimer);
  },
}).mount('#app');
