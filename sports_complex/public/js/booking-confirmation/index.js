const { createApp } = Vue;

// frappe.call() already pops its own "Message" dialog for any server-side
// frappe.throw() before the call's promise even rejects - showing our own
// generic Swal on top of that every time was a second, less specific
// dialog stacked over whatever the server actually said (see the same fix
// already applied in book-facility/index.js and my-bookings/index.js -
// this file was missed at the time). Skip our own fallback whenever the
// server already explained itself, and keep it only for genuinely
// unexpected failures (network errors, etc.) that have nothing else on
// screen to explain them.
//
// The reject value frappe.call()'s .catch() hands back is the raw jqXHR,
// not the parsed response body, so the real field lives at
// err.responseJSON._server_messages (checking err._server_messages
// directly is always undefined) - see the other two files' fix for the
// full explanation.
function hasServerMessage(err) {
  if (!err) return false;
  if (err._server_messages) return true;
  if (err.responseJSON && err.responseJSON._server_messages) return true;
  return false;
}

const CANCELLABLE_STATUSES = ['Draft', 'Payment Pending', 'Confirmed'];
const STATUS_BADGE_CLASS = {
  Draft: 'bk-badge-grey',
  'Payment Pending': 'bk-badge-yellow',
  Confirmed: 'bk-badge-blue',
  'Checked-In': 'bk-badge-yellow',
  Completed: 'bk-badge-total',
  Cancelled: 'bk-badge-red',
  'No-show': 'bk-badge-red',
};

createApp({
  delimiters: ['[[', ']]'],
  data() {
    return {
      doc: window.doc || null,
      token: window.token || null,
      paying: false,
      cancelling: false,
      paymentPopup: null,
      paymentPollTimer: null,
    };
  },
  computed: {
    canCancel() {
      return this.doc && CANCELLABLE_STATUSES.includes(this.doc.booking_status);
    },
    statusBadgeClass() {
      return this.doc ? (STATUS_BADGE_CLASS[this.doc.booking_status] || 'bk-badge-grey') : '';
    },
    directionsUrl() {
      // Prefer the venue's own pin (lat/lon dropped on the map) - falls
      // back to a plain address/city text query so the link still works
      // for a venue whose admin hasn't geocoded it yet. Google Maps'
      // universal cross-platform directions URL: opens the Maps app on
      // mobile, maps.google.com on desktop, no API key required either
      // way.
      if (!this.doc) return null;
      if (this.doc.venue_lat != null && this.doc.venue_lon != null) {
        return `https://www.google.com/maps/dir/?api=1&destination=${this.doc.venue_lat},${this.doc.venue_lon}`;
      }
      const query = [this.doc.venue_address, this.doc.venue_city].filter(Boolean).join(', ');
      return query ? `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(query)}` : null;
    },
  },
  methods: {
    formatAmount(amount) {
      return Number(amount || 0).toLocaleString(undefined, {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      });
    },
    payNow() {
      this.paying = true;
      frappe.call(
        'sports_complex.sports_complex.doctype.facility_booking.facility_booking.get_booking_payment_link',
        { facility_booking: this.doc.name, token: this.token }
      ).then(r => {
        this.paying = false;
        if (r.message) {
          this.openPaymentPopup(r.message);
        } else {
          Swal.fire('Error', 'Could not create a payment link. Please try again.', 'error');
        }
      }).catch((err) => {
        this.paying = false;
        if (!hasServerMessage(err)) {
          Swal.fire('Error', 'Could not create a payment link. Please try again.', 'error');
        }
        // The booking's own state may have moved since this page loaded -
        // exactly the case get_booking_payment_link()'s "no longer
        // Payment Pending" guard exists for (an old tab left open past an
        // auto-cancel, a staff override, etc.). Refresh so the Pay Now
        // button and status badge reflect reality instead of leaving the
        // guest able to just retry the same failing call.
        this.refreshStatus();
      });
    },
    openPaymentPopup(url) {
      // A named popup instead of a plain new tab, so this page stays put
      // and can poll the booking's status while it's open - the moment
      // Paystack reports payment received we flip the status badge over
      // and close the popup automatically instead of leaving the guest to
      // notice and refresh on their own.
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
          this.refreshStatus();
          return;
        }
        this.refreshStatus();
      }, 3000);
    },
    refreshStatus() {
      if (!this.doc || !this.doc.name) return;
      frappe.call(
        'sports_complex.sports_complex.doctype.facility_booking.facility_booking.get_booking_status',
        { facility_booking: this.doc.name, token: this.token }
      ).then(r => {
        if (!r.message) return;
        this.doc = r.message;
        if (r.message.booking_status === 'Confirmed' || r.message.payment_status === 'Paid') {
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
        // Non-fatal background check - the guest can still complete
        // payment in the popup and see the updated status on their next
        // visit to this page even if one poll fails.
      });
    },
    cancelBooking() {
      Swal.fire({
        title: 'Cancel this booking?',
        icon: 'warning',
        showCancelButton: true,
        confirmButtonText: 'Yes, cancel it',
      }).then(result => {
        if (!result.isConfirmed) return;
        this.cancelling = true;
        frappe.call(
          'sports_complex.sports_complex.doctype.facility_booking.facility_booking.request_cancellation',
          { facility_booking: this.doc.name, token: this.token }
        ).then(() => {
          this.doc.booking_status = 'Cancelled';
          Swal.fire('Cancelled', 'Your booking has been cancelled.', 'success');
        }).catch((err) => {
          if (!hasServerMessage(err)) {
            Swal.fire('Error', 'Could not cancel this booking. It may be past the cancellation window.', 'error');
          }
        }).finally(() => {
          this.cancelling = false;
        });
      });
    },
  },
  beforeUnmount() {
    if (this.paymentPollTimer) clearInterval(this.paymentPollTimer);
  },
}).mount('#app');
