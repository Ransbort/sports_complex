<template>
  <div class="mx-auto max-w-5xl px-4 py-8 sm:px-6" :class="{ 'min-h-full flex flex-col': step !== 'grid' }">

    <!-- Step 0: browse bookable coaches -->
    <div v-if="step === 'grid'">
      <h1 class="text-2xl font-extrabold text-slate-800">Book a Coach</h1>
      <p class="mb-6 text-slate-500">Book a one-on-one coaching session with one of our coaches.</p>

      <p v-if="loadingCoaches" class="py-16 text-center text-slate-400">Loading coaches...</p>
      <p v-else-if="!coaches.length" class="py-16 text-center text-slate-400">No coaches are open for booking right now.</p>

      <div v-else class="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
        <div
          v-for="c in coaches" :key="c.name"
          class="flex flex-col overflow-hidden rounded-2xl border border-slate-900/5 bg-white shadow-[0_4px_20px_rgba(15,23,42,0.06)] transition hover:-translate-y-0.5 hover:shadow-[0_8px_28px_rgba(15,23,42,0.12)]"
        >
          <div
            class="relative flex h-36 items-center justify-center bg-slate-100 bg-cover bg-center"
            :style="c.photo ? { backgroundImage: 'url(' + c.photo + ')' } : {}"
          >
            <i v-if="!c.photo" class="bi bi-person-badge text-3xl text-slate-300"></i>
            <span
              class="absolute bottom-2.5 left-2.5 rounded-full px-2.5 py-1 text-xs font-semibold text-white"
              :style="{ backgroundColor: c.open_slots_today ? 'var(--portal-primary, #16a34a)' : '#6b7280' }"
            >
              {{ c.open_slots_today ? c.open_slots_today + ' open today' : 'Fully booked today' }}
            </span>
          </div>
          <div class="flex flex-1 flex-col p-4">
            <h6 class="mb-1 font-bold text-slate-800">{{ c.coach_name }}</h6>
            <p v-if="c.specializations && c.specializations.length" class="mb-1 flex flex-wrap gap-1">
              <span
                v-for="s in c.specializations" :key="s"
                class="rounded-full px-2.5 py-0.5 text-xs font-semibold"
                style="background: color-mix(in srgb, var(--portal-primary, #16a34a) 10%, transparent); color: var(--portal-primary, #16a34a);"
              >{{ s }}</span>
            </p>
            <p class="mb-3 text-lg font-bold text-slate-800">
              {{ fmt(c.hourly_rate) }} <span class="text-sm font-normal text-slate-400">/ hour</span>
            </p>
            <button
              class="mt-auto w-full rounded-xl border-0 bg-[var(--portal-primary,#16a34a)] py-2.5 font-semibold text-white hover:bg-[var(--portal-primary-hover,#15803d)]"
              @click="pickCoach(c)"
            >
              Book Now
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Step 1: date/slot pick, identity, result -->
    <div v-else class="mx-auto flex w-full max-w-lg flex-1 items-start justify-center">
      <div class="w-full rounded-2xl border border-slate-900/5 bg-white shadow-[0_4px_24px_rgba(15,23,42,0.08)]">
        <div class="border-b border-slate-900/5 px-6 py-5">
          <button type="button" class="mb-2 border-0 bg-transparent p-0 text-sm text-slate-500 hover:text-slate-700" @click="backToGrid">
            <i class="bi bi-arrow-left"></i> Back
          </button>
          <div class="flex items-center gap-2 font-bold text-slate-800">
            <i class="bi bi-person-badge text-[var(--portal-primary,#16a34a)]"></i>
            <span>{{ selectedCoach.coach_name }}</span>
          </div>
          <p v-if="selectedCoach.specializations && selectedCoach.specializations.length" class="m-0 text-sm text-slate-500">
            {{ selectedCoach.specializations.join(', ') }}
          </p>
        </div>

        <div class="p-6">

          <!-- result -->
          <div v-if="step === 'result'" class="py-4 text-center">
            <i class="bi bi-check-circle-fill text-5xl" style="color: var(--portal-primary, #16a34a);"></i>
            <h5 class="mt-3 font-bold text-slate-800">Session booked!</h5>
            <p class="text-slate-500">{{ resultMessage }}</p>
            <a
              v-if="paymentLink" :href="paymentLink"
              class="mt-2 inline-block rounded-xl bg-[var(--portal-primary,#16a34a)] px-5 py-2.5 font-semibold text-white hover:bg-[var(--portal-primary-hover,#15803d)]"
            >
              Pay Now
            </a>
            <div class="mt-3"><router-link to="/" class="text-sm text-slate-500 hover:text-slate-700">Back to Home</router-link></div>
          </div>

          <template v-else>
            <!-- date + slots -->
            <div class="mb-4">
              <label class="mb-1 block text-sm font-semibold text-slate-600">Date</label>
              <input
                type="date" v-model="selectedDate" :min="today" @change="loadSlots"
                class="w-52 rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-[var(--portal-primary,#16a34a)] focus:outline-none focus:ring-1 focus:ring-[var(--portal-primary,#16a34a)]"
              >
            </div>

            <div class="mb-4" v-if="selectedDate">
              <label class="mb-1 block text-sm font-semibold text-slate-600">Available Times</label>
              <p v-if="loadingSlots" class="text-sm text-slate-400">Loading availability...</p>
              <p v-else-if="!slots.length" class="text-sm text-slate-400">No open times on this date - try another day.</p>
              <div v-else class="grid grid-cols-2 gap-2 sm:grid-cols-3">
                <button
                  v-for="s in slots" :key="s.start_time"
                  type="button"
                  class="rounded-lg border px-2 py-2 text-sm font-semibold text-slate-700"
                  :class="selectedSlot && selectedSlot.start_time === s.start_time
                    ? 'text-white'
                    : 'border-slate-200 hover:border-[var(--portal-primary,#16a34a)]'"
                  :style="selectedSlot && selectedSlot.start_time === s.start_time
                    ? { backgroundColor: 'var(--portal-primary, #16a34a)', borderColor: 'var(--portal-primary, #16a34a)' }
                    : {}"
                  @click="selectedSlot = s"
                >{{ shortTime(s.start_time) }} - {{ shortTime(s.end_time) }}</button>
              </div>
            </div>

            <template v-if="selectedSlot">
              <hr class="my-5 border-slate-100">

              <!-- guest identity -->
              <div v-if="!auth.isLoggedIn" class="mb-4">
                <label class="mb-1 block text-sm font-semibold text-slate-600">Your Email</label>
                <div class="flex gap-2">
                  <input
                    type="email" v-model="email" :disabled="otpSent" placeholder="you@example.com"
                    class="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-[var(--portal-primary,#16a34a)] focus:outline-none focus:ring-1 focus:ring-[var(--portal-primary,#16a34a)]"
                  >
                  <button
                    v-if="!otpSent" type="button" :disabled="sendingOtp" @click="sendOtp"
                    class="rounded-lg border border-[var(--portal-primary,#16a34a)] px-3 py-2 text-sm font-semibold text-[var(--portal-primary,#16a34a)] hover:bg-[var(--portal-primary,#16a34a)] hover:text-white disabled:opacity-60"
                  >
                    {{ sendingOtp ? 'Sending...' : 'Send Code' }}
                  </button>
                  <button
                    v-else type="button" @click="otpSent = false"
                    class="rounded-lg border border-slate-300 px-3 py-2 text-sm font-semibold text-slate-600 hover:bg-slate-50"
                  >
                    Change
                  </button>
                </div>
                <div v-if="otpSent" class="mt-2">
                  <label class="mb-1 block text-sm font-semibold text-slate-600">Verification Code</label>
                  <input
                    type="text" v-model="otp" maxlength="6" placeholder="6-digit code"
                    class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-[var(--portal-primary,#16a34a)] focus:outline-none focus:ring-1 focus:ring-[var(--portal-primary,#16a34a)]"
                  >
                </div>
              </div>

              <div class="mb-4">
                <label class="mb-1 block text-sm font-semibold text-slate-600">Player's Full Name</label>
                <input
                  type="text" v-model="playerName" placeholder="Who's training?"
                  class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-[var(--portal-primary,#16a34a)] focus:outline-none focus:ring-1 focus:ring-[var(--portal-primary,#16a34a)]"
                >
              </div>
              <div class="mb-4">
                <label class="mb-1 block text-sm font-semibold text-slate-600">Player's Date of Birth</label>
                <input
                  type="date" v-model="dateOfBirth" :max="today"
                  class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-[var(--portal-primary,#16a34a)] focus:outline-none focus:ring-1 focus:ring-[var(--portal-primary,#16a34a)]"
                >
              </div>

              <div v-if="isMinor" class="mb-4 rounded-lg border border-amber-200 bg-amber-50 p-3.5">
                <p class="mb-2 text-sm font-bold text-slate-700">Guardian details (required for players under 18)</p>
                <div class="grid grid-cols-1 gap-2 sm:grid-cols-2">
                  <input type="text" v-model="guardianName" placeholder="Guardian name" class="rounded-lg border border-slate-300 px-3 py-2 text-sm">
                  <input type="text" v-model="guardianRelationship" placeholder="Relationship to player" class="rounded-lg border border-slate-300 px-3 py-2 text-sm">
                  <input type="text" v-model="guardianContact" placeholder="Guardian phone" class="rounded-lg border border-slate-300 px-3 py-2 text-sm">
                  <input type="email" v-model="guardianEmail" placeholder="Guardian email" class="rounded-lg border border-slate-300 px-3 py-2 text-sm">
                </div>
                <label class="mt-2 flex items-center gap-2 text-sm text-slate-600">
                  <input type="checkbox" v-model="consentGiven">
                  I am this player's parent/guardian and consent to this booking.
                </label>
              </div>

              <div class="mb-4" v-if="auth.isLoggedIn">
                <label class="mb-1 block text-sm font-semibold text-slate-600">Notes (optional)</label>
                <textarea v-model="notes" rows="2" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"></textarea>
              </div>

              <button
                class="mt-3 flex w-full items-center justify-center gap-2 rounded-xl border-0 bg-[var(--portal-primary,#16a34a)] py-3 font-semibold text-white hover:bg-[var(--portal-primary-hover,#15803d)] disabled:opacity-60"
                :disabled="!canSubmit || submitting" @click="submitBooking"
              >
                <i v-if="submitting" class="bi bi-arrow-repeat animate-spin"></i>
                {{ submitting ? 'Booking...' : 'Confirm Booking - ' + fmt(sessionFee) }}
              </button>
              <p v-if="errorMessage" class="mt-2 mb-0 text-sm text-red-600">{{ errorMessage }}</p>
            </template>
          </template>
        </div>
      </div>
    </div>

  </div>
</template>

<script>
import { call, hasServerMessage } from '@/api/frappe';
import { useAuthStore } from '@/stores/auth';

// Same "remember this browser after a verified OTP" pattern (and the same
// storage key) as the pre-migration book-coach page - a guest who already
// verified there stays remembered here too, rather than being asked
// again just because the booking flow moved into this app.
const REMEMBER_KEY = 'sc_coach_booking_remember_v1';

function loadRemembered() {
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

function saveRemembered(email, token) {
  try {
    localStorage.setItem(REMEMBER_KEY, JSON.stringify({ email: (email || '').trim().toLowerCase(), token }));
  } catch (e) {
    // Nothing to do if storage isn't available.
  }
}

export default {
  setup() {
    return { auth: useAuthStore() };
  },
  data() {
    const now = new Date();
    const today = now.toISOString().slice(0, 10);
    const remembered = loadRemembered();
    return {
      coaches: [],
      loadingCoaches: true,
      currencySymbol: (window.portalBoot && window.portalBoot.currency_symbol) || '',
      step: 'grid', // 'grid' -> 'detail' -> 'result'
      today,
      selectedCoach: {},
      selectedDate: '',
      slots: [],
      loadingSlots: false,
      selectedSlot: null,
      email: remembered ? remembered.email : '',
      otp: '',
      otpSent: false,
      sendingOtp: false,
      guestRememberToken: remembered ? remembered.token : '',
      playerName: '',
      dateOfBirth: '',
      guardianName: '',
      guardianRelationship: '',
      guardianContact: '',
      guardianEmail: '',
      consentGiven: false,
      notes: '',
      submitting: false,
      errorMessage: '',
      resultMessage: '',
      paymentLink: '',
    };
  },
  computed: {
    isMinor() {
      if (!this.dateOfBirth) return false;
      const dob = new Date(this.dateOfBirth);
      if (isNaN(dob.getTime())) return false;
      const now = new Date();
      let age = now.getFullYear() - dob.getFullYear();
      const m = now.getMonth() - dob.getMonth();
      if (m < 0 || (m === 0 && now.getDate() < dob.getDate())) age--;
      return age < 18;
    },
    sessionFee() {
      if (!this.selectedSlot || !this.selectedCoach.hourly_rate) return 0;
      return Number(this.selectedCoach.hourly_rate) * this.slotHours(this.selectedSlot);
    },
    canSubmit() {
      if (!this.selectedSlot || !this.playerName || !this.dateOfBirth) return false;
      if (this.isMinor && !(this.guardianName && this.guardianContact && this.consentGiven)) return false;
      if (!this.auth.isLoggedIn) {
        if (!this.email) return false;
        if (!this.guestRememberToken && !this.otpSent) return false;
        if (!this.guestRememberToken && this.otpSent && !this.otp) return false;
      }
      return true;
    },
  },
  created() {
    this.loadCoaches();
  },
  methods: {
    loadCoaches() {
      this.loadingCoaches = true;
      call('sports_complex.sports_complex.doctype.training_session.training_session.list_bookable_coaches')
        .then((coaches) => {
          this.coaches = coaches || [];
        })
        .finally(() => {
          this.loadingCoaches = false;
        });
    },
    fmt(amount) {
      return this.currencySymbol + Number(amount || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    },
    shortTime(value) {
      const parts = String(value).split(':');
      let h = parseInt(parts[0], 10);
      const m = parts[1];
      const ampm = h >= 12 ? 'PM' : 'AM';
      h = h % 12 || 12;
      return h + ':' + m + ' ' + ampm;
    },
    slotHours(slot) {
      const [sh, sm] = slot.start_time.split(':').map(Number);
      const [eh, em] = slot.end_time.split(':').map(Number);
      return (eh * 60 + em - (sh * 60 + sm)) / 60;
    },
    pickCoach(c) {
      this.selectedCoach = c;
      this.step = 'detail';
      this.selectedDate = this.today;
      this.selectedSlot = null;
      this.playerName = '';
      this.dateOfBirth = '';
      this.otp = '';
      this.otpSent = false;
      this.errorMessage = '';
      this.loadSlots();
    },
    backToGrid() {
      this.step = 'grid';
      this.selectedSlot = null;
    },
    loadSlots() {
      this.selectedSlot = null;
      if (!this.selectedDate) {
        this.slots = [];
        return;
      }
      this.loadingSlots = true;
      call('sports_complex.sports_complex.doctype.training_session.training_session.get_coach_available_slots', {
        coach: this.selectedCoach.name,
        date: this.selectedDate,
      }).then((slots) => {
        this.slots = slots || [];
      }).finally(() => {
        this.loadingSlots = false;
      });
    },
    sendOtp() {
      if (!this.email) return;
      this.sendingOtp = true;
      call('sports_complex.utils.guest_booking.send_booking_otp', { email: this.email })
        .then(() => {
          this.otpSent = true;
        })
        .catch((err) => {
          if (!hasServerMessage(err)) {
            window.Swal && window.Swal.fire({ icon: 'error', title: 'Could not send code', text: 'Please try again.' });
          }
        })
        .finally(() => {
          this.sendingOtp = false;
        });
    },
    submitBooking() {
      if (!this.canSubmit || this.submitting) return;
      this.submitting = true;
      this.errorMessage = '';

      const payload = {
        coach: this.selectedCoach.name,
        date: this.selectedDate,
        start_time: this.selectedSlot.start_time,
        end_time: this.selectedSlot.end_time,
        full_name: this.playerName,
        date_of_birth: this.dateOfBirth,
        notes: this.notes,
        guardian_name: this.guardianName,
        guardian_relationship: this.guardianRelationship,
        guardian_contact: this.guardianContact,
        guardian_email: this.guardianEmail,
        consent_given: this.consentGiven ? 1 : 0,
      };

      let method = 'sports_complex.sports_complex.doctype.training_session.training_session.create_training_booking';
      if (!this.auth.isLoggedIn) {
        method = 'sports_complex.sports_complex.doctype.training_session.training_session.create_guest_training_booking';
        payload.email = this.email;
        payload.otp = this.otp;
        payload.remember_token = this.guestRememberToken;
      }

      call(method, payload).then((msg) => {
        msg = msg || {};
        if (!this.auth.isLoggedIn && msg.remember_token) {
          saveRemembered(this.email, msg.remember_token);
          this.guestRememberToken = msg.remember_token;
        }
        this.resultMessage = 'Your session with ' + this.selectedCoach.coach_name + ' on ' + this.selectedDate + ' is booked.';
        this.paymentLink = msg.payment_link || '';
        this.step = 'result';
      }).catch((err) => {
        if (!hasServerMessage(err)) {
          this.errorMessage = 'Could not book this session - please try again.';
        }
      }).finally(() => {
        this.submitting = false;
      });
    },
  },
};
</script>
