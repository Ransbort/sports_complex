<template>
  <div class="mx-auto max-w-6xl min-h-full px-4 py-8 sm:px-6">
    <!-- Identity gate: a logged-in customer (auth.isLoggedIn) skips this
         entirely; a guest sees it until a remembered token silently
         checks out or they verify a fresh email/OTP - same shape as the
         legacy www/my-bookings page's own showAuthGate, and the exact
         same OTP endpoints/remember-token mechanics (see
         sports_complex/utils/guest_booking.py). -->
    <div v-if="showAuthGate" class="mx-auto max-w-md">
      <div class="overflow-hidden rounded-2xl border border-slate-900/5 bg-white shadow-[0_4px_24px_rgba(15,23,42,0.08)]">
        <div class="flex items-center gap-2 border-b border-slate-100 px-6 py-4 font-semibold text-slate-800">
          <i class="bi bi-calendar2-week text-[var(--portal-primary,#16a34a)]"></i>
          My Bookings
        </div>
        <div class="p-6">
          <div v-if="checkingRemembered" class="flex justify-center py-4">
            <i class="bi bi-arrow-repeat animate-spin text-xl text-[var(--portal-primary,#16a34a)]"></i>
          </div>
          <template v-else>
            <p class="mb-4 text-sm text-slate-500">Enter the email you booked with to look up your bookings.</p>
            <form v-if="!otpSent" class="space-y-4" @submit.prevent="sendOtp">
              <div>
                <label class="mb-1 block text-sm font-medium text-slate-500">Email</label>
                <input type="email" v-model="guestEmail" required class="w-full rounded-lg border-[1px] border-slate-300 px-3 py-2 text-sm focus:border-[var(--portal-primary,#16a34a)] focus:outline-none focus:ring-1 focus:ring-[var(--portal-primary,#16a34a)]">
              </div>
              <button
                type="submit"
                class="flex w-full items-center justify-center rounded-xl border-0 bg-[var(--portal-primary,#16a34a)] py-3 font-semibold text-white hover:bg-[var(--portal-primary-hover,#15803d)] disabled:opacity-60"
                :disabled="!canSendOtp || sendingOtp"
              >
                {{ sendingOtp ? 'Sending...' : 'Send Verification Code' }}
              </button>
            </form>
            <form v-else class="space-y-4" @submit.prevent="verifyAndLoad">
              <p class="text-sm text-slate-500">A verification code was sent to <strong>{{ guestEmail }}</strong>.</p>
              <div>
                <label class="mb-1 block text-sm font-medium text-slate-500">Verification Code</label>
                <input
                  type="text" inputmode="numeric" maxlength="6" v-model="guestOtp" required
                  class="w-full rounded-lg border-[1px] border-slate-300 px-3 py-2 text-sm focus:border-[var(--portal-primary,#16a34a)] focus:outline-none focus:ring-1 focus:ring-[var(--portal-primary,#16a34a)]"
                >
              </div>
              <button
                type="submit"
                class="flex w-full items-center justify-center rounded-xl border-0 bg-[var(--portal-primary,#16a34a)] py-3 font-semibold text-white hover:bg-[var(--portal-primary-hover,#15803d)] disabled:opacity-60"
                :disabled="!guestOtp || loading"
              >
                {{ loading ? 'Checking...' : 'View My Bookings' }}
              </button>
              <p class="mb-0 text-center text-sm text-slate-500">
                <span v-if="otpCountdown > 0">Resend code in {{ otpCountdown }}s</span>
                <button v-else type="button" class="border-0 bg-transparent p-0 font-semibold text-[var(--portal-primary,#16a34a)] disabled:text-slate-400" :disabled="sendingOtp" @click="resendOtp">
                  {{ sendingOtp ? 'Resending...' : 'Resend Code' }}
                </button>
              </p>
              <button type="button" class="block w-full border-0 bg-transparent p-0 text-center text-sm text-slate-500 hover:text-slate-700" @click="otpSent = false">&larr; Use a different email</button>
            </form>
          </template>
        </div>
      </div>
    </div>

    <!-- Full table: shown once identity is settled. -->
    <div v-else>
      <div v-if="isGuest" class="mb-6 flex justify-end">
        <button type="button" class="border-0 bg-transparent p-0 text-sm font-semibold text-slate-500 hover:text-slate-700" @click="reset">&larr; Check a different email</button>
      </div>

      <p v-if="loading" class="py-16 text-center text-slate-400">Loading your bookings...</p>

      <template v-else-if="loaded">
        <p v-if="!bookings.length" class="py-16 text-center text-slate-400">No bookings found.</p>

        <template v-else>
          <div class="mb-5 flex flex-wrap items-end gap-3 rounded-2xl border border-slate-900/5 bg-white p-4 shadow-[0_2px_12px_rgba(15,23,42,0.04)]">
            <div>
              <label class="mb-1.5 block text-xs font-medium text-slate-500">Status</label>
              <div class="relative">
                <select v-model="filterStatus" class="h-9 min-w-[9.5rem] appearance-none rounded-lg border-[1px] border-slate-300 bg-white pl-3 pr-8 text-sm text-slate-700 focus:border-[var(--portal-primary,#16a34a)] focus:outline-none focus:ring-2 focus:ring-[var(--portal-primary,#16a34a)]/20 transition-colors">
                  <option value="">All Statuses</option>
                  <option v-for="s in statusOptions" :key="s" :value="s">{{ s }}</option>
                </select>
                <i class="bi bi-chevron-down pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-xs text-slate-400"></i>
              </div>
            </div>
            <div>
              <label class="mb-1.5 block text-xs font-medium text-slate-500">Facility</label>
              <div class="relative">
                <select v-model="filterFacility" class="h-9 min-w-[9.5rem] appearance-none rounded-lg border-[1px] border-slate-300 bg-white pl-3 pr-8 text-sm text-slate-700 focus:border-[var(--portal-primary,#16a34a)] focus:outline-none focus:ring-2 focus:ring-[var(--portal-primary,#16a34a)]/20 transition-colors">
                  <option value="">All Facilities</option>
                  <option v-for="f in facilityOptions" :key="f" :value="f">{{ f }}</option>
                </select>
                <i class="bi bi-chevron-down pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-xs text-slate-400"></i>
              </div>
            </div>
            <div>
              <label class="mb-1.5 block text-xs font-medium text-slate-500">Search Facility</label>
              <div class="relative">
                <i class="bi bi-search pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-xs text-slate-400"></i>
                <input type="text" v-model="filterSearch" placeholder="Search..." class="h-9 w-48 rounded-lg border-[1px] border-slate-300 bg-white pl-8 pr-3 text-sm text-slate-700 placeholder:text-slate-400 focus:border-[var(--portal-primary,#16a34a)] focus:outline-none focus:ring-2 focus:ring-[var(--portal-primary,#16a34a)]/20 transition-colors">
              </div>
            </div>
            <div v-if="selectedFacilityDirectionsUrl">
              <label class="mb-1.5 block text-xs font-medium text-transparent select-none" aria-hidden="true">Directions</label>
              <a
                :href="selectedFacilityDirectionsUrl" target="_blank" rel="noopener noreferrer"
                class="flex h-9 items-center gap-1 whitespace-nowrap rounded-lg px-1 text-sm font-semibold text-[var(--portal-primary,#16a34a)] hover:underline"
              >
                <i class="bi bi-geo-alt"></i> Get Directions
              </a>
            </div>
            <button v-if="hasActiveFilters" type="button" class="mb-0.5 inline-flex h-9 items-center gap-1 border-0 bg-transparent p-0 text-sm font-semibold text-[var(--portal-primary,#16a34a)] hover:text-[var(--portal-primary-hover,#15803d)]" @click="clearFilters">
              <i class="bi bi-x-circle"></i> Clear Filters
            </button>
            <div v-if="checkedInBookings.length" class="ml-auto flex flex-wrap items-center justify-end gap-2">
              <div
                v-for="b in checkedInBookings" :key="b.name"
                class="flex items-center gap-1.5 rounded-full bg-amber-50 px-3 py-1.5 text-xs font-medium text-amber-700"
              >
                <i class="bi bi-hourglass-split"></i>
                <span class="font-semibold">{{ b.facility_name }}</span>
                <span>{{ checkinCountdown(b) }}</span>
              </div>
            </div>
          </div>

          <p v-if="!filteredBookings.length" class="py-16 text-center text-slate-400">No bookings match your filters.</p>

          <template v-else>
            <div class="overflow-x-auto rounded-2xl border border-slate-900/5 bg-white shadow-[0_4px_20px_rgba(15,23,42,0.06)]">
              <table class="w-full min-w-[860px] text-left text-sm">
                <thead class="border-b border-slate-100 text-xs font-semibold uppercase tracking-wide text-slate-400">
                  <tr>
                    <th class="px-4 py-3">Facility</th>
                    <th class="px-4 py-3">Date</th>
                    <th class="px-4 py-3">Time</th>
                    <th class="px-4 py-3">Status</th>
                    <th class="px-4 py-3">Amount<template v-if="currencySymbol"> ({{ currencySymbol }})</template></th>
                    <th class="px-4 py-3"></th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-slate-100">
                  <tr v-for="g in pagedGroups" :key="g.key">
                    <td class="px-4 py-3">
                      <div class="font-semibold text-slate-800">
                        {{ g.bookings[0].facility_name }}
                        <span v-if="g.bookings.length > 1" class="ml-1 rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-500">{{ g.bookings.length }} slots</span>
                      </div>
                    </td>
                    <td class="px-4 py-3 text-slate-600">{{ groupDateLabel(g.bookings) }}</td>
                    <td class="px-4 py-3 text-slate-600">
                      <template v-if="g.bookings.length === 1">{{ g.bookings[0].start_time }}&ndash;{{ g.bookings[0].end_time }}</template>
                      <template v-else>{{ g.bookings.length }} time slots</template>
                    </td>
                    <td class="px-4 py-3">
                      <template v-if="groupStatusSummary(g.bookings)">
                        <span class="whitespace-nowrap rounded-full px-2.5 py-1 text-xs font-semibold" :class="statusClass(groupStatusSummary(g.bookings))">{{ groupStatusSummary(g.bookings) }}</span>
                        <div v-if="groupStatusSummary(g.bookings) === 'Cancelled' && g.bookings[0].cancellation_reason" class="mt-1 max-w-[160px] truncate text-xs text-slate-400" :title="g.bookings[0].cancellation_reason">{{ g.bookings[0].cancellation_reason }}</div>
                      </template>
                      <span v-else class="whitespace-nowrap rounded-full bg-slate-100 px-2.5 py-1 text-xs font-semibold text-slate-600">Mixed status</span>
                    </td>
                    <td class="px-4 py-3 text-slate-700">
                      {{ fmt(g.bookings.length > 1 ? g.bookings[0].invoice_amount : g.bookings[0].total_amount) }}
                      <div v-if="g.bookings.length > 1" class="mt-1 text-xs text-slate-400">for {{ g.bookings.length }} slots booked together</div>
                      <div v-if="g.bookings.length === 1 && g.bookings[0].booking_status === 'No-show' && g.bookings[0].no_show_penalty_amount" class="mt-1 flex items-center gap-1 text-xs text-amber-600">
                        <i class="bi bi-exclamation-triangle"></i> No-show penalty: {{ fmt(g.bookings[0].no_show_penalty_amount) }}
                      </div>
                    </td>
                    <td class="px-4 py-3 text-right">
                      <div class="flex items-center justify-end gap-2">
                        <button
                          v-if="groupPaymentTarget(g.bookings)" type="button"
                          class="inline-flex items-center gap-1.5 whitespace-nowrap rounded-lg border-0 bg-[var(--portal-primary,#16a34a)] px-3 py-1.5 text-xs font-semibold text-white hover:bg-[var(--portal-primary-hover,#15803d)] disabled:opacity-60"
                          :disabled="payingBooking === groupPaymentTarget(g.bookings).name || waitingBooking === groupPaymentTarget(g.bookings).name"
                          @click="payNow(groupPaymentTarget(g.bookings))"
                        >
                          <i v-if="payingBooking === groupPaymentTarget(g.bookings).name || waitingBooking === groupPaymentTarget(g.bookings).name" class="bi bi-arrow-repeat animate-spin"></i>
                          {{ payingBooking === groupPaymentTarget(g.bookings).name ? 'Starting...' : (waitingBooking === groupPaymentTarget(g.bookings).name ? 'Waiting...' : 'Pay Now') }}
                        </button>
                        <span v-if="groupPaymentTarget(g.bookings) && waitingBooking === groupPaymentTarget(g.bookings).name" class="flex items-center gap-1 text-xs text-slate-400">
                          <i class="bi bi-arrow-repeat animate-spin text-[var(--portal-primary,#16a34a)]"></i>
                          Confirming payment&hellip;
                        </span>
                        <router-link :to="bookingTo(g.bookings[0])" class="whitespace-nowrap rounded-lg border border-[var(--portal-primary,#16a34a)] px-3 py-1.5 text-xs font-semibold text-[var(--portal-primary,#16a34a)] hover:bg-[var(--portal-primary,#16a34a)] hover:text-white">View</router-link>
                      </div>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div class="mt-3 flex flex-wrap items-center justify-between gap-2">
              <p class="text-sm text-slate-400">Showing {{ pageRangeStart }}&ndash;{{ pageRangeEnd }} of {{ groupedBookings.length }} booking{{ groupedBookings.length === 1 ? '' : 's' }}</p>
              <div v-if="totalPages > 1" class="flex items-center gap-3">
                <button type="button" class="rounded-lg border-[1px] border-slate-300 px-3 py-1.5 text-sm font-semibold text-slate-600 disabled:opacity-40" :disabled="currentPage <= 1" @click="prevPage">&laquo; Prev</button>
                <span class="text-sm text-slate-500">Page {{ currentPage }} of {{ totalPages }}</span>
                <button type="button" class="rounded-lg border-[1px] border-slate-300 px-3 py-1.5 text-sm font-semibold text-slate-600 disabled:opacity-40" :disabled="currentPage >= totalPages" @click="nextPage">Next &raquo;</button>
              </div>
            </div>
          </template>
        </template>
      </template>
    </div>
  </div>
</template>

<script>
import { call, hasServerMessage } from '@/api/frappe';
import { useAuthStore } from '@/stores/auth';

const STATUS_BADGE_CLASS = {
  Draft: 'bg-slate-100 text-slate-600',
  'Payment Pending': 'bg-amber-100 text-amber-700',
  Confirmed: 'bg-blue-100 text-blue-700',
  'Checked-In': 'bg-amber-100 text-amber-700',
  Completed: 'bg-emerald-100 text-emerald-700',
  Cancelled: 'bg-red-100 text-red-700',
  'No-show': 'bg-red-100 text-red-700',
};

// Same key the legacy www/my-bookings page used, deliberately - a guest
// who already verified an email there stays remembered here too instead
// of being asked to re-verify just because the page moved into this app.
const REMEMBER_KEY = 'sc_my_bookings_remember_v1';

function loadRememberedIdentity() {
  try {
    const raw = localStorage.getItem(REMEMBER_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (parsed && parsed.email && parsed.token) return parsed;
  } catch (e) {
    // Storage unavailable - fall back to the normal email/OTP form.
  }
  return null;
}

export default {
  setup() {
    return { auth: useAuthStore() };
  },
  data() {
    const remembered = loadRememberedIdentity();
    return {
      // Read the same way BookFacility.vue's own currencySymbol already
      // is - window.portalBoot is set server-side once per page load
      // (see www/portal/index.py), same source both pages pull from.
      currencySymbol: (window.portalBoot && window.portalBoot.currency_symbol) || '',
      guestEmail: (remembered && remembered.email) || '',
      guestOtp: '',
      otpSent: false,
      sendingOtp: false,
      otpCountdown: 0,
      otpCountdownTimer: null,
      verified: false,
      checkingRemembered: false,
      rememberedToken: remembered ? remembered.token : null,
      loading: false,
      loaded: false,
      bookings: [],
      customerName: '',
      filterStatus: '',
      filterFacility: '',
      filterSearch: '',
      currentPage: 1,
      pageSize: 10,
      payingBooking: null,
      paymentPopup: null,
      paymentPollTimer: null,
      waitingBooking: null,
      now: Date.now(),
      checkinTimer: null,
    };
  },
  computed: {
    isGuest() {
      return !this.auth.isLoggedIn;
    },
    canSendOtp() {
      return /\S+@\S+\.\S+/.test(this.guestEmail);
    },
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
    checkedInBookings() {
      // Unfiltered on purpose - a session in progress belongs in the
      // filter bar regardless of what Status/Facility/Search are
      // currently narrowing the table down to.
      return this.bookings.filter(b => b.booking_status === 'Checked-In');
    },
    selectedFacilityDirectionsUrl() {
      // Venue is per-facility, not per-booking-list, so this only has one
      // right answer once the Facility filter has actually narrowed the
      // table down to a single facility - any booking for it carries the
      // same venue info, so the first match is as good as any.
      if (!this.filterFacility) return null;
      const match = this.bookings.find(b => b.facility_name === this.filterFacility);
      return match ? this.directionsUrl(match) : null;
    },
    // Sibling bookings that share one Sales Invoice (a multi-slot cart
    // checkout - see facility_booking.py's list_my_bookings) are shown as
    // a single row instead of one row per slot: opening "View" on any one
    // of them already lands on the confirmation page's own full
    // breakdown (see BookingConfirmation.vue / _get_invoice_group()), so
    // repeating all N rows here just repeated the same shared total N
    // times. Grouped on filteredBookings (not the raw bookings list) so
    // a status/facility/search filter that only matches some siblings
    // still only shows those - same as before, just consolidated when
    // every matching sibling is present together.
    groupedBookings() {
      const groups = [];
      const byInvoice = new Map();
      this.filteredBookings.forEach((b) => {
        const key = b.sales_invoice || `single:${b.name}`;
        let group = byInvoice.get(key);
        if (!group) {
          group = { key, bookings: [] };
          byInvoice.set(key, group);
          groups.push(group);
        }
        group.bookings.push(b);
      });
      return groups;
    },
    totalPages() {
      return Math.max(1, Math.ceil(this.groupedBookings.length / this.pageSize));
    },
    pagedGroups() {
      const page = Math.min(this.currentPage, this.totalPages);
      const start = (page - 1) * this.pageSize;
      return this.groupedBookings.slice(start, start + this.pageSize);
    },
    pageRangeStart() {
      return this.groupedBookings.length ? (Math.min(this.currentPage, this.totalPages) - 1) * this.pageSize + 1 : 0;
    },
    pageRangeEnd() {
      return Math.min(this.pageRangeStart + this.pageSize - 1, this.groupedBookings.length);
    },
  },
  watch: {
    filterStatus() { this.currentPage = 1; },
    filterFacility() { this.currentPage = 1; },
    filterSearch() { this.currentPage = 1; },
  },
  created() {
    // auth.isLoggedIn is already known synchronously from window.portalBoot
    // (see stores/auth.js) by the time this component is created, so
    // checkingRemembered/loadBookings can both be driven from here rather
    // than needing to know isGuest inside data() itself.
    const remembered = loadRememberedIdentity();
    if (this.isGuest && remembered) {
      this.checkingRemembered = true;
      this.tryRememberedLogin();
    } else if (!this.isGuest) {
      this.loadBookings();
    }
  },
  mounted() {
    // Drives the live countdown shown under Checked-In bookings (see
    // checkinCountdown()) - ticks every second purely to re-render that
    // computed-from-`now` string, same pattern as paymentPollTimer below.
    this.checkinTimer = setInterval(() => {
      this.now = Date.now();
    }, 1000);
  },
  methods: {
    fmt(amount) {
      return Number(amount || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    },
    statusClass(status) {
      return STATUS_BADGE_CLASS[status] || 'bg-slate-100 text-slate-600';
    },
    groupDateLabel(bookings) {
      const dates = [...new Set(bookings.map(b => b.booking_date))].sort();
      return dates.length === 1 ? dates[0] : `${dates[0]} to ${dates[dates.length - 1]}`;
    },
    groupStatusSummary(bookings) {
      // Siblings on one invoice can still diverge later (one no-shows,
      // one gets cancelled, one gets checked in) - null here means
      // "don't pretend these all share one status", not an error.
      const statuses = new Set(bookings.map(b => b.booking_status));
      return statuses.size === 1 ? bookings[0].booking_status : null;
    },
    groupPaymentTarget(bookings) {
      // get_booking_payment_link() bills the whole shared invoice
      // regardless of which sibling's name is passed, so any Payment
      // Pending sibling works here - falls back to null (no Pay Now
      // button) rather than the first sibling when none are pending, so
      // a fully-paid or fully-cancelled group doesn't show a stale button.
      return bookings.find(b => b.booking_status === 'Payment Pending') || null;
    },
    checkinCountdown(b) {
      // Bookings have no dedicated check-in timestamp field - the
      // "number of hours booked" is the slot itself, so the countdown is
      // simply the time remaining until this slot's own end_time.
      if (b.booking_status !== 'Checked-In' || !b.booking_date || !b.end_time) return null;
      const end = new Date(`${b.booking_date}T${b.end_time}`);
      if (Number.isNaN(end.getTime())) return null;
      const diffMs = end.getTime() - this.now;
      if (diffMs <= 0) return 'Session time elapsed';
      const totalSeconds = Math.floor(diffMs / 1000);
      const hours = Math.floor(totalSeconds / 3600);
      const minutes = Math.floor((totalSeconds % 3600) / 60);
      const seconds = totalSeconds % 60;
      const pad = n => String(n).padStart(2, '0');
      return `${hours > 0 ? hours + ':' : ''}${pad(minutes)}:${pad(seconds)} remaining`;
    },
    bookingTo(b) {
      return { path: `/booking-confirmation/${b.name}`, query: b.token ? { token: b.token } : {} };
    },
    directionsUrl(b) {
      if (b.venue_lat != null && b.venue_lon != null) {
        return `https://www.google.com/maps/dir/?api=1&destination=${b.venue_lat},${b.venue_lon}`;
      }
      const query = [b.venue_address, b.venue_city].filter(Boolean).join(', ');
      return query ? `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(query)}` : null;
    },
    sendOtp() {
      this.sendingOtp = true;
      call('sports_complex.utils.guest_booking.send_booking_otp', { email: this.guestEmail })
        .then(() => {
          this.otpSent = true;
          this.sendingOtp = false;
          this.startOtpCountdown();
        }).catch((err) => {
          if (!hasServerMessage(err)) {
            window.Swal && window.Swal.fire('Error', 'Could not send the verification code. Please check the email address and try again.', 'error');
          }
          this.sendingOtp = false;
        });
    },
    resendOtp() {
      if (this.otpCountdown > 0 || this.sendingOtp) return;
      this.guestOtp = '';
      this.sendingOtp = true;
      call('sports_complex.utils.guest_booking.send_booking_otp', { email: this.guestEmail })
        .then(() => {
          this.sendingOtp = false;
          this.startOtpCountdown();
        }).catch((err) => {
          if (!hasServerMessage(err)) {
            window.Swal && window.Swal.fire('Error', 'Could not resend the verification code. Please try again.', 'error');
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
      call(
        'sports_complex.sports_complex.doctype.facility_booking.facility_booking.list_my_bookings',
        { email: this.guestEmail, otp: this.guestOtp }
      ).then((result) => {
        this.bookings = (result && result.bookings) || [];
        this.customerName = (result && result.customer_name) || '';
        this.rememberIdentity(this.guestEmail, result && result.remember_token);
        this.verified = true;
        this.loaded = true;
        this.loading = false;
      }).catch((err) => {
        if (!hasServerMessage(err)) {
          window.Swal && window.Swal.fire('Error', 'Invalid or expired code. Please try again.', 'error');
        }
        this.loading = false;
      });
    },
    loadBookings() {
      this.loading = true;
      call('sports_complex.sports_complex.doctype.facility_booking.facility_booking.list_my_bookings', {})
        .then((result) => {
          this.bookings = (result && result.bookings) || [];
          this.customerName = (result && result.customer_name) || '';
          this.loaded = true;
          this.loading = false;
        }).catch((err) => {
          if (!hasServerMessage(err)) {
            window.Swal && window.Swal.fire('Error', 'Could not load your bookings.', 'error');
          }
          this.loading = false;
        });
    },
    tryRememberedLogin() {
      this.loading = true;
      call(
        'sports_complex.sports_complex.doctype.facility_booking.facility_booking.list_my_bookings',
        { email: this.guestEmail, remember_token: this.rememberedToken }
      ).then((result) => {
        if (!result || !result.verified) {
          this.forgetIdentity();
          this.checkingRemembered = false;
          this.loading = false;
          return;
        }
        this.bookings = result.bookings || [];
        this.customerName = result.customer_name || '';
        this.rememberIdentity(this.guestEmail, result.remember_token);
        this.verified = true;
        this.loaded = true;
        this.loading = false;
        this.checkingRemembered = false;
      }).catch(() => {
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
        // Storage unavailable - the convenience just doesn't persist.
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
      this.guestEmail = '';
      this.loaded = false;
      this.bookings = [];
      this.customerName = '';
      this.otpCountdown = 0;
      this.clearFilters();
      this.forgetIdentity();
      if (this.otpCountdownTimer) {
        clearInterval(this.otpCountdownTimer);
        this.otpCountdownTimer = null;
      }
    },
    // --- Paystack "Pay Now", ported from BookFacility.vue's own payNow()/
    // watchPayment()/refreshPaymentStatus() - same popup + poll pattern,
    // just parameterized per-row instead of against a single just-created
    // result, since My Bookings can have several Payment Pending rows at
    // once and each needs its own booking name/token.
    payNow(booking) {
      this.payingBooking = booking.name;
      call(
        'sports_complex.sports_complex.doctype.facility_booking.facility_booking.get_booking_payment_link',
        { facility_booking: booking.name, token: booking.token }
      ).then((url) => {
        this.payingBooking = null;
        if (!url) return;
        this.openPaymentPopup(url, booking);
      }).catch((err) => {
        this.payingBooking = null;
        if (!hasServerMessage(err)) {
          window.Swal && window.Swal.fire('Error', 'Could not start payment. Please try again.', 'error');
        }
      });
    },
    openPaymentPopup(url, booking) {
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
      this.waitingBooking = booking.name;
      this.watchPayment(booking);
    },
    watchPayment(booking) {
      if (this.paymentPollTimer) clearInterval(this.paymentPollTimer);
      this.paymentPollTimer = setInterval(() => {
        const popup = this.paymentPopup;
        if (popup && popup.closed) {
          clearInterval(this.paymentPollTimer);
          this.paymentPollTimer = null;
          this.paymentPopup = null;
          this.refreshBookingStatus(booking).finally(() => {
            if (this.waitingBooking === booking.name) this.waitingBooking = null;
          });
          return;
        }
        this.refreshBookingStatus(booking);
      }, 3000);
    },
    refreshBookingStatus(booking) {
      return call(
        'sports_complex.sports_complex.doctype.facility_booking.facility_booking.get_booking_status',
        { facility_booking: booking.name, token: booking.token }
      ).then((status) => {
        if (!status) return;
        if (status.booking_status === 'Confirmed' || status.payment_status === 'Paid') {
          booking.booking_status = status.booking_status;
          booking.payment_status = status.payment_status;
          if (this.paymentPollTimer) {
            clearInterval(this.paymentPollTimer);
            this.paymentPollTimer = null;
          }
          if (this.paymentPopup && !this.paymentPopup.closed) {
            this.paymentPopup.close();
          }
          this.paymentPopup = null;
          if (this.waitingBooking === booking.name) this.waitingBooking = null;
          // Bring the opener tab to the front - the guest's attention may
          // still be on the payment popup that was just closed.
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
        // Non-fatal - the guest can still complete payment in the popup and
        // check status later via "View".
      });
    },
  },
  beforeUnmount() {
    if (this.otpCountdownTimer) clearInterval(this.otpCountdownTimer);
    if (this.paymentPollTimer) clearInterval(this.paymentPollTimer);
    if (this.checkinTimer) clearInterval(this.checkinTimer);
  },
};
</script>
