const { createApp } = Vue;

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
    };
  },
  computed: {
    canCancel() {
      return this.doc && CANCELLABLE_STATUSES.includes(this.doc.booking_status);
    },
    statusBadgeClass() {
      return this.doc ? (STATUS_BADGE_CLASS[this.doc.booking_status] || 'bk-badge-grey') : '';
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
        if (r.message) {
          window.open(r.message, '_blank');
        } else {
          Swal.fire('Error', 'Could not create a payment link. Please try again.', 'error');
        }
      }).catch(() => {
        Swal.fire('Error', 'Could not create a payment link. Please try again.', 'error');
      }).finally(() => {
        this.paying = false;
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
        }).catch(() => {
          Swal.fire('Error', 'Could not cancel this booking. It may be past the cancellation window.', 'error');
        }).finally(() => {
          this.cancelling = false;
        });
      });
    },
  },
}).mount('#app');
