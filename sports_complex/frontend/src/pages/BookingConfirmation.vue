<template>
  <div class="mx-auto max-w-lg px-4 py-8 sm:px-6">
    <router-link
      to="/my-bookings"
      class="mb-3 inline-flex items-center gap-1.5 border-0 bg-transparent p-0 text-sm font-semibold text-slate-500 hover:text-slate-700"
    >
      <i class="bi bi-arrow-left"></i> My Bookings
    </router-link>

    <p v-if="loading" class="py-16 text-center text-slate-400">Loading booking...</p>

    <div
      v-else-if="!doc"
      class="flex items-start gap-3 rounded-2xl border border-red-200 bg-red-50 p-4 text-red-800"
    >
      <i class="bi bi-x-circle-fill mt-0.5 text-xl text-red-600"></i>
      <div>
        <p class="mb-1 font-bold">Booking Not Found</p>
        <p class="m-0 text-sm">This booking couldn't be found, or you don't have access to it.</p>
      </div>
    </div>

    <div v-else class="overflow-hidden rounded-2xl border border-slate-900/5 bg-white shadow-[0_4px_24px_rgba(15,23,42,0.08)]">
      <div class="flex items-center gap-2 border-b border-slate-900/5 px-6 py-5 font-bold text-slate-800">
        <i class="bi bi-calendar2-check text-[var(--portal-primary,#16a34a)]"></i>
        <span>Booking {{ doc.name }}</span>
        <span class="ml-auto rounded-full px-2.5 py-1 text-xs font-bold uppercase tracking-wide" :class="statusBadgeClass">
          {{ doc.booking_status }}
        </span>
      </div>

      <ul class="list-none divide-y divide-slate-100 pl-[0px]" style="margin-bottom: 0;">
        <template v-if="doc.cart_bookings && doc.cart_bookings.length">
          <li class="bg-slate-50 px-6 py-3 text-xs text-slate-500">
            This booking was paid together with {{ doc.cart_bookings.length - 1 }} other slot{{ doc.cart_bookings.length > 2 ? 's' : '' }} in the same checkout - the amount below covers all of them.
          </li>
          <li
            v-for="cb in doc.cart_bookings" :key="cb.name"
            class="flex items-center justify-between gap-2 px-6 py-3"
            :class="{ 'bg-[color-mix(in_srgb,var(--portal-primary,#16a34a)_5%,transparent)]': cb.name === doc.name }"
          >
            <span class="flex flex-col gap-0.5">
              <span class="text-sm font-semibold text-slate-800">{{ cb.facility_name }}</span>
              <span class="text-xs text-slate-500">{{ cb.booking_date }} &middot; {{ cb.start_time }}&ndash;{{ cb.end_time }}</span>
            </span>
            <span class="rounded-full bg-slate-100 px-2.5 py-1 text-sm font-semibold text-slate-800">{{ fmt(cb.total_amount) }}</span>
          </li>
        </template>
        <template v-else>
          <li class="flex items-center justify-between gap-2 px-6 py-3">
            <span class="text-sm text-slate-500">Facility</span>
            <span class="rounded-full bg-slate-100 px-2.5 py-1 text-sm font-semibold text-slate-800">{{ doc.sports_facility }}</span>
          </li>
          <li class="flex items-center justify-between gap-2 px-6 py-3">
            <span class="text-sm text-slate-500">Date</span>
            <span class="rounded-full bg-slate-100 px-2.5 py-1 text-sm font-semibold text-slate-800">{{ doc.booking_date }}</span>
          </li>
          <li class="flex items-center justify-between gap-2 px-6 py-3">
            <span class="text-sm text-slate-500">Time</span>
            <span class="rounded-full bg-slate-100 px-2.5 py-1 text-sm font-semibold text-slate-800">{{ doc.start_time }} &ndash; {{ doc.end_time }}</span>
          </li>
        </template>

        <li v-if="doc.venue_name || doc.venue_address" class="px-6 py-3">
          <p class="mb-1 text-sm text-slate-500">Venue</p>
          <p v-if="doc.venue_name" class="m-0 text-sm font-semibold text-slate-800">{{ doc.venue_name }}</p>
          <p v-if="doc.venue_address" class="m-0 text-sm text-slate-500">
            {{ doc.venue_address }}<span v-if="doc.venue_city">, {{ doc.venue_city }}</span>
          </p>
          <a
            v-if="directionsUrl" :href="directionsUrl" target="_blank" rel="noopener noreferrer"
            class="mt-1.5 inline-flex items-center gap-1.5 text-sm font-semibold text-[var(--portal-primary,#16a34a)]"
          >
            <i class="bi bi-signpost-2-fill"></i> Get Directions
          </a>
        </li>

        <li class="flex items-center justify-between gap-2 px-6 py-3" style="background: color-mix(in srgb, var(--portal-primary, #16a34a) 6%, transparent);">
          <span class="text-sm font-semibold text-slate-800">{{ doc.cart_bookings && doc.cart_bookings.length ? 'Total Amount' : 'Amount' }}</span>
          <span class="rounded-full px-3 py-1.5 text-sm font-bold text-white" style="background: var(--portal-primary, #16a34a);">{{ fmt(doc.invoice_amount) }}</span>
        </li>

        <li v-if="doc.booking_status === 'No-show' && doc.no_show_penalty_amount" class="flex items-center justify-between gap-2 px-6 py-3">
          <span class="text-sm text-slate-500">No-Show Penalty</span>
          <span class="rounded-full bg-red-100 px-2.5 py-1 text-sm font-semibold text-red-700">{{ fmt(doc.no_show_penalty_amount) }}</span>
        </li>

        <li v-if="doc.booking_status === 'Cancelled' && doc.cancellation_reason" class="bg-red-50 px-6 py-3">
          <p class="mb-1 text-sm text-slate-500">Cancellation Reason</p>
          <p class="m-0 text-sm text-red-800">{{ doc.cancellation_reason }}</p>
        </li>
      </ul>

      <div class="flex flex-col gap-3 px-6 py-5">
        <button
          v-if="doc.booking_status === 'Payment Pending'" type="button"
          class="flex w-full items-center justify-center gap-2 rounded-2xl border-0 bg-[var(--portal-primary,#16a34a)] py-3 font-semibold text-white hover:bg-[var(--portal-primary-hover,#15803d)] disabled:opacity-60" style="border-radius: 1rem;"
          :disabled="paying" @click="payNow"
        >
          <i v-if="paying" class="bi bi-arrow-repeat animate-spin"></i>
          {{ paying ? 'Opening...' : 'Pay Now' }}
        </button>
        <button
          v-if="canCancel" type="button"
          class="flex w-full items-center justify-center rounded-2xl border-[1px] border-[#fecaca] bg-[transparent] py-3 font-semibold text-red-600 transition-colors duration-200 hover:border-[#dc2626] hover:bg-[#dc2626] hover:text-white disabled:opacity-60" style="border-radius: 1rem;"
          :disabled="cancelling" @click="cancelBooking"
        >
          {{ cancelling ? 'Cancelling...' : 'Cancel Booking' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script>
import { call, hasServerMessage } from '@/api/frappe';

const CANCELLABLE_STATUSES = ['Draft', 'Payment Pending', 'Confirmed'];
const STATUS_BADGE_CLASS = {
  Draft: 'bg-slate-100 text-slate-600',
  'Payment Pending': 'bg-amber-100 text-amber-800',
  Confirmed: 'bg-blue-100 text-blue-700',
  'Checked-In': 'bg-amber-100 text-amber-800',
  Completed: 'bg-[var(--portal-primary,#16a34a)] text-white',
  Cancelled: 'bg-red-100 text-red-700',
  'No-show': 'bg-red-100 text-red-700',
};

export default {
  data() {
    return {
      loading: true,
      doc: null,
      currencySymbol: (window.portalBoot && window.portalBoot.currency_symbol) || '',
      paying: false,
      cancelling: false,
      paymentPopup: null,
      paymentPollTimer: null,
    };
  },
  computed: {
    token() {
      return this.$route.query.token || null;
    },
    canCancel() {
      return this.doc && CANCELLABLE_STATUSES.includes(this.doc.booking_status);
    },
    statusBadgeClass() {
      if (!this.doc) return '';
      return STATUS_BADGE_CLASS[this.doc.booking_status] || 'bg-slate-100 text-slate-600';
    },
    directionsUrl() {
      // Prefer the venue's own pin - falls back to an address/city text
      // query so the link still works for a venue that isn't geocoded
      // yet. Google's universal directions URL needs no API key and
      // opens the Maps app on mobile, maps.google.com on desktop.
      if (!this.doc) return null;
      if (this.doc.venue_lat != null && this.doc.venue_lon != null) {
        return `https://www.google.com/maps/dir/?api=1&destination=${this.doc.venue_lat},${this.doc.venue_lon}`;
      }
      const query = [this.doc.venue_address, this.doc.venue_city].filter(Boolean).join(', ');
      return query ? `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(query)}` : null;
    },
  },
  mounted() {
    this.loadStatus();
  },
  beforeUnmount() {
    if (this.paymentPollTimer) clearInterval(this.paymentPollTimer);
  },
  methods: {
    fmt(amount) {
      return this.currencySymbol + Number(amount || 0).toLocaleString(undefined, {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      });
    },
    loadStatus() {
      this.loading = true;
      call(
        'sports_complex.sports_complex.doctype.facility_booking.facility_booking.get_booking_status',
        { facility_booking: this.$route.params.name, token: this.token }
      ).then((status) => {
        this.doc = status || null;
        this.loading = false;
      }).catch(() => {
        // Not found or no access - same generic message either way, so a
        // guessed booking name can't be used to tell a real booking that
        // isn't the guest's own from one that simply doesn't exist.
        this.doc = null;
        this.loading = false;
      });
    },
    payNow() {
      this.paying = true;
      call(
        'sports_complex.sports_complex.doctype.facility_booking.facility_booking.get_booking_payment_link',
        { facility_booking: this.doc.name, token: this.token }
      ).then((url) => {
        this.paying = false;
        if (url) {
          this.openPaymentPopup(url);
        } else {
          window.Swal && window.Swal.fire('Error', 'Could not create a payment link. Please try again.', 'error');
        }
      }).catch((err) => {
        this.paying = false;
        if (!hasServerMessage(err)) {
          window.Swal && window.Swal.fire('Error', 'Could not create a payment link. Please try again.', 'error');
        }
        // The booking's own state may have moved on since this page
        // loaded - refresh so the button/badge reflect reality instead
        // of leaving the guest able to just retry the same failing call.
        this.loadStatus();
      });
    },
    openPaymentPopup(url) {
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
          this.loadStatus();
          return;
        }
        this.refreshStatus();
      }, 3000);
    },
    // Same call as loadStatus() but doesn't toggle the page's own loading
    // spinner - this runs silently in the background every few seconds
    // while the payment popup is open.
    refreshStatus() {
      call(
        'sports_complex.sports_complex.doctype.facility_booking.facility_booking.get_booking_status',
        { facility_booking: this.doc.name, token: this.token }
      ).then((status) => {
        if (!status) return;
        this.doc = status;
        if (status.booking_status === 'Confirmed' || status.payment_status === 'Paid') {
          if (this.paymentPollTimer) {
            clearInterval(this.paymentPollTimer);
            this.paymentPollTimer = null;
          }
          if (this.paymentPopup && !this.paymentPopup.closed) {
            this.paymentPopup.close();
          }
          this.paymentPopup = null;
          // The success dialog fires in this (opener) window/tab, which the
          // guest may have left unfocused while the payment popup had their
          // attention - bring it to the front so they actually see it.
          window.focus();
          window.Swal && window.Swal.fire({
            title: 'Payment received',
            text: 'Your booking is confirmed.',
            icon: 'success',
            iconColor: 'var(--portal-primary, #16a34a)',
            confirmButtonColor: 'var(--portal-primary, #16a34a)',
          });
        }
      }).catch(() => {
        // Non-fatal background check - the guest can still complete
        // payment in the popup and see the updated status next visit
        // even if one poll fails.
      });
    },
    cancelBooking() {
      if (!window.Swal) return;
      window.Swal.fire({
        title: 'Cancel this booking?',
        icon: 'warning',
        showCancelButton: true,
        confirmButtonText: 'Yes, cancel it',
      }).then((result) => {
        if (!result.isConfirmed) return;
        this.cancelling = true;
        call(
          'sports_complex.sports_complex.doctype.facility_booking.facility_booking.request_cancellation',
          { facility_booking: this.doc.name, token: this.token }
        ).then(() => {
          this.doc.booking_status = 'Cancelled';
          window.Swal.fire('Cancelled', 'Your booking has been cancelled.', 'success');
        }).catch((err) => {
          if (!hasServerMessage(err)) {
            window.Swal.fire('Error', 'Could not cancel this booking. It may be past the cancellation window.', 'error');
          }
        }).finally(() => {
          this.cancelling = false;
        });
      });
    },
  },
};
</script>
