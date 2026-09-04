<template>
  <div class="mx-auto max-w-5xl px-4 py-8 sm:px-6" :class="{ 'min-h-full flex flex-col': step !== 'grid' }">

    <!-- Step 0: browse all bookable facilities -->
    <div v-if="step === 'grid'">
      <p class="mb-6 text-slate-500">Browse facilities and reserve a time slot.</p>

      <p v-if="loadingFacilities" class="py-16 text-center text-slate-400">Loading facilities...</p>
      <p v-else-if="!facilities.length" class="py-16 text-center text-slate-400">No facilities are open for booking right now.</p>

      <div v-else class="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
        <div
          v-for="f in facilities" :key="f.name"
          class="flex flex-col overflow-hidden rounded-2xl border border-slate-900/5 bg-white shadow-[0_4px_20px_rgba(15,23,42,0.06)] transition hover:-translate-y-0.5 hover:shadow-[0_8px_28px_rgba(15,23,42,0.12)]"
        >
          <div
            class="relative flex h-36 items-center justify-center bg-slate-100 bg-cover bg-center"
            :style="f.image ? { backgroundImage: 'url(' + f.image + ')' } : {}"
          >
            <i v-if="!f.image" class="bi bi-image text-3xl text-slate-300"></i>
            <span
              class="absolute bottom-2.5 left-2.5 rounded-full px-2.5 py-1 text-xs font-semibold text-white"
              :style="{ backgroundColor: f.open_slots_today ? 'var(--portal-primary, #16a34a)' : '#6b7280' }"
            >
              {{ f.open_slots_today ? f.open_slots_today + ' open today' : 'Fully booked today' }}
            </span>
          </div>
          <div class="flex flex-1 flex-col p-4">
            <h6 class="mb-1 font-bold text-slate-800">{{ f.facility_name }}</h6>
            <p v-if="f.surface_type" class="mb-1 text-sm text-slate-500">{{ f.surface_type }}</p>
            <p class="mb-3 text-lg font-bold text-slate-800">
              {{ fmt(f.hourly_rate) }} <span class="text-sm font-normal text-slate-400">/ hour</span>
            </p>
            <button
              class="mt-auto w-full rounded-xl border-0 bg-[var(--portal-primary,#16a34a)] py-2.5 font-semibold text-white hover:bg-[var(--portal-primary-hover,#15803d)]"
              @click="pickFacility(f)"
            >
              Book Now
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Steps 1-3: date/slot pick, identity, result -->
    <div v-else class="w-full">
      <button
        v-if="step === 'browse'" type="button"
        class="mb-3 inline-flex items-center gap-1.5 border-0 bg-transparent p-0 text-sm font-semibold text-slate-500 hover:text-slate-700"
        @click="backToGrid"
      >
        <i class="bi bi-arrow-left"></i> All facilities
      </button>
      <div class="flex w-full overflow-hidden rounded-2xl border border-slate-900/5 bg-white shadow-[0_4px_24px_rgba(15,23,42,0.08)]">
        <!-- Column 1: the facility's own photo (from Sports Facility's
             `image` field via list_bookable_facilities). Hidden below md
             so the calendar/form column keeps its full width on narrow
             screens rather than being squeezed by a photo that has no
             room to earn its keep there. -->
        <div
          v-if="selectedFacilityInfo.image"
          class="relative max-md:hidden w-3/5 shrink-0 bg-slate-100 bg-cover bg-center"
          :style="{ backgroundImage: 'url(' + selectedFacilityInfo.image + ')' }"
        >
          <div class="absolute inset-0 bg-gradient-to-t from-slate-900/70 via-slate-900/10 to-transparent"></div>
          <div class="absolute inset-x-0 bottom-0 p-5 text-white">
            <p v-if="selectedFacilityInfo.surface_type" class="mb-0.5 text-xs font-semibold uppercase tracking-wide text-white/75">
              {{ selectedFacilityInfo.surface_type }}
            </p>
            <p class="text-lg font-bold leading-tight">{{ selectedFacilityInfo.facility_name }}</p>
          </div>
        </div>
        <div v-else class="max-md:hidden flex w-3/5 shrink-0 items-center justify-center bg-slate-100">
          <i class="bi bi-image text-4xl text-slate-300"></i>
        </div>

        <!-- Column 2: the existing step-by-step flow, unchanged below. -->
        <div class="flex min-w-0 flex-1 flex-col">
        <div class="flex flex-wrap items-center justify-between gap-2 border-b border-slate-900/5 px-6 py-5">
          <div class="flex items-center gap-2 font-bold text-slate-800">
            <i class="bi bi-calendar2-check text-[var(--portal-primary,#16a34a)]"></i>
            <span>Book a Facility</span>
          </div>
          <p class="m-0 flex items-center gap-1.5 text-xs text-slate-500">
            <span class="inline-block h-1.5 w-1.5 rounded-full" style="background: var(--portal-primary, #16a34a);"></span> open
            <span class="inline-block h-1.5 w-1.5 rounded-full bg-slate-300"></span> fully booked
          </p>
        </div>

        <!-- Step 1: pick date, check availability -->
        <div v-if="step === 'browse'" class="p-6">
          <p class="mb-5 flex items-center gap-2 rounded-lg px-4 py-3 font-semibold text-slate-800" style="background: color-mix(in srgb, var(--portal-primary, #16a34a) 8%, transparent);">
            <i class="bi bi-geo-alt"></i>
            {{ selectedFacilityInfo.facility_name || selectedFacility }}
            <span v-if="selectedFacilityInfo.surface_type" class="font-normal text-slate-500">&middot; {{ selectedFacilityInfo.surface_type }}</span>
          </p>

          <div class="mb-2 p-4">
            <div class="mb-2 flex items-center justify-between">
              <button
                type="button"
                class="flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 text-slate-700 disabled:opacity-40"
                :disabled="isPrevMonthDisabled" @click="prevMonth"
              ><i class="bi bi-chevron-left"></i></button>
              <span class="text-sm font-semibold text-slate-800">{{ monthLabel }}</span>
              <button
                type="button"
                class="flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 text-slate-700"
                @click="nextMonth"
              ><i class="bi bi-chevron-right"></i></button>
            </div>
            <div class="mb-2 grid grid-cols-7 gap-1.5 text-center text-xs font-semibold uppercase text-slate-400">
              <span v-for="d in dowLabels" :key="d">{{ d }}</span>
            </div>
            <div class="grid min-h-[246px] grid-cols-7 gap-1.5 text-center">
              <span v-for="n in leadingBlanks" :key="'b' + n" class="h-9"></span>
              <button
                v-for="day in daysInMonth" :key="day" type="button"
                class="relative flex h-9 items-center justify-center rounded-lg text-sm font-semibold text-slate-800 disabled:cursor-default disabled:text-slate-300"
                :class="[
                  dayHasSelection(day) ? 'border-2' : (isToday(day) ? 'border' : 'border border-transparent'),
                  isSelected(day) ? 'text-white' : 'hover:bg-[color-mix(in_srgb,var(--portal-primary,#16a34a)_8%,transparent)]',
                ]"
                :style="dayStyle(day)"
                :disabled="isPastDay(day)"
                @click="selectDay(day)"
              >
                {{ day }}
                <span
                  v-if="!isPastDay(day) && monthAvailability[dayKey(day)] !== undefined"
                  class="absolute bottom-1 left-1/2 h-1.5 w-1.5 -translate-x-1/2 rounded-full"
                  :style="{ backgroundColor: monthAvailability[dayKey(day)] > 0 ? (isSelected(day) ? '#fff' : 'var(--portal-primary, #16a34a)') : '#d1d5db' }"
                ></span>
              </button>
            </div>
            <p class="mt-2 mb-0 h-5 text-center text-sm text-slate-400">{{ loadingMonth ? 'Loading availability...' : '' }}</p>
          </div>

          <div v-if="cart.length" class="mt-4 flex items-center justify-between gap-4 rounded-xl px-4 py-3.5 font-semibold text-slate-800" style="background: color-mix(in srgb, var(--portal-primary, #16a34a) 8%, transparent);">
            <span>{{ cart.length }} slot{{ cart.length === 1 ? '' : 's' }} selected &middot; {{ fmt(cartTotal) }}</span>
            <button
              type="button"
              class="rounded-lg border-0 bg-[var(--portal-primary,#16a34a)] px-4 py-2 text-sm font-semibold text-white hover:bg-[var(--portal-primary-hover,#15803d)]"
              @click="step = 'details'"
            >
              Continue
            </button>
          </div>
        </div>

        <!-- Step 2: confirm identity + book -->
        <div v-else-if="step === 'details'" class="p-6">
          <p class="mb-5 flex items-center gap-2 rounded-lg px-4 py-3 font-semibold text-slate-800" style="background: color-mix(in srgb, var(--portal-primary, #16a34a) 8%, transparent);">
            <i class="bi bi-geo-alt"></i>
            {{ selectedFacilityInfo.facility_name || selectedFacility }}
          </p>

          <ul class="mb-1 max-h-72 divide-y divide-slate-100 overflow-y-auto border-y border-slate-100">
            <li v-for="group in groupedCart" :key="group.booking_date + group.start_time" class="flex items-center justify-between gap-2 py-3">
              <span class="text-sm text-slate-700">{{ group.booking_date }} &middot; {{ group.start_time }}&ndash;{{ group.end_time }}</span>
              <div class="flex shrink-0 items-center gap-2">
                <span class="text-sm font-medium text-slate-800">{{ fmt(groupPrice(group)) }}</span>
                <button
                  type="button"
                  class="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border-0 bg-transparent text-lg text-slate-500 hover:bg-slate-100"
                  aria-label="Remove" @click="removeGroupFromCart(group)"
                >
                  <i class="bi bi-x-lg"></i>
                </button>
              </div>
            </li>
          </ul>
          <p class="mb-5 text-right text-slate-800">Total: <strong>{{ fmt(cartTotal) }}</strong></p>

          <template v-if="auth.isLoggedIn">
            <div class="mb-4">
              <label class="mb-1 block text-sm font-medium text-slate-500">Notes (optional)</label>
              <textarea
                v-model="notes" rows="2" maxlength="500" placeholder="Anything we should know about this booking?"
                class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-[var(--portal-primary,#16a34a)] focus:outline-none focus:ring-1 focus:ring-[var(--portal-primary,#16a34a)]"
              ></textarea>
            </div>
            <button
              class="border-0 flex w-full items-center justify-center gap-2 rounded-xl bg-[var(--portal-primary,#16a34a)] py-3 font-semibold text-white hover:bg-[var(--portal-primary-hover,#15803d)] disabled:opacity-60"
              :disabled="booking || !cart.length" @click="confirmBooking"
            >
              <i v-if="booking" class="bi bi-arrow-repeat animate-spin"></i>
              {{ booking ? 'Booking...' : 'Confirm Booking' }}
            </button>
          </template>

          <template v-else>
            <form v-if="!otpSent" class="space-y-4" @submit.prevent="proceedFromDetails">
              <div>
                <label class="mb-1 block text-sm font-medium text-slate-500">Full Name</label>
                <input type="text" v-model="guestName" required class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-[var(--portal-primary,#16a34a)] focus:outline-none focus:ring-1 focus:ring-[var(--portal-primary,#16a34a)]">
              </div>
              <div>
                <label class="mb-1 block text-sm font-medium text-slate-500">Email</label>
                <input type="email" v-model="guestEmail" required class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-[var(--portal-primary,#16a34a)] focus:outline-none focus:ring-1 focus:ring-[var(--portal-primary,#16a34a)]">
              </div>
              <div>
                <label class="mb-1 block text-sm font-medium text-slate-500">Phone (optional)</label>
                <input type="tel" v-model="guestPhone" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-[var(--portal-primary,#16a34a)] focus:outline-none focus:ring-1 focus:ring-[var(--portal-primary,#16a34a)]">
              </div>
              <div>
                <label class="mb-1 block text-sm font-medium text-slate-500">Notes (optional)</label>
                <textarea
                  v-model="notes" rows="2" maxlength="500" placeholder="Anything we should know about this booking?"
                  class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-[var(--portal-primary,#16a34a)] focus:outline-none focus:ring-1 focus:ring-[var(--portal-primary,#16a34a)]"
                ></textarea>
              </div>
              <div class="rounded-lg border border-slate-200 px-3.5 py-3">
                <label class="flex items-start gap-2 text-sm font-medium text-slate-700">
                  <input type="checkbox" v-model="wantsAccount" class="mt-0.5 h-4 w-4 rounded border-slate-300 text-[var(--portal-primary,#16a34a)] focus:ring-[var(--portal-primary,#16a34a)]">
                  Create an account so I can sign in and see all my bookings
                </label>
                <input
                  v-if="wantsAccount" type="password" v-model="accountPassword" required minlength="8"
                  placeholder="Choose a password (min. 8 characters)" autocomplete="new-password"
                  class="mt-2.5 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-[var(--portal-primary,#16a34a)] focus:outline-none focus:ring-1 focus:ring-[var(--portal-primary,#16a34a)]"
                >
              </div>
              <p v-if="guestVerified" class="flex flex-wrap items-center gap-1.5 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2.5 text-sm text-emerald-800">
                <i class="bi bi-patch-check-fill text-emerald-600"></i>
                Verified as <strong>{{ guestEmail }}</strong> - no code needed right now.
                <button type="button" class="ml-auto border-0 bg-transparent p-0 font-semibold text-[var(--portal-primary,#16a34a)]" @click="forgetGuestVerification">Not you?</button>
              </p>
              <button
                type="submit"
                class="border-0 flex w-full items-center justify-center rounded-xl bg-[var(--portal-primary,#16a34a)] py-3 font-semibold text-white hover:bg-[var(--portal-primary-hover,#15803d)] disabled:opacity-60"
                :disabled="detailsSubmitDisabled"
              >
                {{ detailsSubmitLabel }}
              </button>
            </form>
            <form v-else class="space-y-4" @submit.prevent="confirmGuestBooking">
              <p class="text-sm text-slate-500">A verification code was sent to <strong>{{ guestEmail }}</strong>.</p>
              <div>
                <label class="mb-1 block text-sm font-medium text-slate-500">Verification Code</label>
                <input
                  type="text" inputmode="numeric" maxlength="6" v-model="guestOtp" required
                  class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-[var(--portal-primary,#16a34a)] focus:outline-none focus:ring-1 focus:ring-[var(--portal-primary,#16a34a)]"
                >
              </div>
              <button
                type="submit"
                class="border-0 flex w-full items-center justify-center gap-2 rounded-xl bg-[var(--portal-primary,#16a34a)] py-3 font-semibold text-white hover:bg-[var(--portal-primary-hover,#15803d)] disabled:opacity-60"
                :disabled="!guestOtp || booking || !cart.length || accountPasswordInvalid"
              >
                <i v-if="booking" class="bi bi-arrow-repeat animate-spin"></i>
                {{ booking ? 'Booking...' : 'Verify & Book' }}
              </button>
              <p class="mb-0 text-center text-sm text-slate-500">
                <span v-if="otpCountdown > 0">Resend code in {{ otpCountdown }}s</span>
                <button v-else type="button" class="border-0 bg-transparent p-0 font-semibold text-[var(--portal-primary,#16a34a)] disabled:text-slate-400" :disabled="sendingOtp" @click="resendOtp">
                  {{ sendingOtp ? 'Resending...' : 'Resend Code' }}
                </button>
              </p>
            </form>
          </template>

          <button type="button" class="mt-3 block w-full border-0 bg-transparent p-0 text-center text-sm text-slate-500 hover:text-slate-700" @click="step = 'browse'">&larr; Add more slots</button>
        </div>

        <!-- Step 3: result -->
        <div v-else-if="step === 'result'" class="p-6 text-center">
          <i class="bi bi-check-circle-fill text-5xl" style="color: var(--portal-primary, #16a34a);"></i>
          <h5 class="mt-3 font-bold text-slate-800">
            {{ result.bookings.length > 1 ? result.bookings.length + ' Bookings' : 'Booking' }}
            {{ result.booking_status === 'Confirmed' ? 'Confirmed' : 'Created' }}
          </h5>
          <ul class="mb-6 mt-4 divide-y divide-slate-100 border-y border-slate-100 text-left">
            <li v-for="b in result.bookings" :key="b.name" class="flex items-center justify-between gap-2 py-2.5">
              <span class="rounded-full bg-slate-100 px-3 py-1.5 text-sm font-semibold text-slate-800">{{ b.name }}</span>
              <router-link :to="bookingViewTo(b)" class="font-semibold text-[var(--portal-primary,#16a34a)]">View</router-link>
            </li>
          </ul>
          <p v-if="accountResult && accountResult.created && accountSignedIn" class="mb-4 flex items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-3.5 py-2.5 text-sm text-emerald-800">
            <i class="bi bi-patch-check-fill text-emerald-600"></i>
            Account created - you're signed in as <strong>{{ guestEmail }}</strong>.
          </p>
          <p v-else-if="accountResult && !accountResult.created" class="mb-4 flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3.5 py-2.5 text-sm text-amber-800">
            <i class="bi bi-exclamation-triangle-fill text-amber-600"></i>
            <span v-if="accountResult.reason === 'exists'">An account already exists for this email - sign in to see all your bookings.</span>
            <span v-else>Your booking is confirmed, but the account couldn't be created right now.</span>
          </p>
          <p v-if="waitingForPayment" class="mb-3 flex items-center justify-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3.5 py-2.5 text-sm text-slate-600">
            <i class="bi bi-arrow-repeat animate-spin text-[var(--portal-primary,#16a34a)]"></i>
            Waiting for payment confirmation...
          </p>
          <button
            v-if="result.payment_link" type="button"
            class="border-0 flex w-full items-center justify-center gap-2 rounded-xl bg-[var(--portal-primary,#16a34a)] py-3 font-semibold text-white hover:bg-[var(--portal-primary-hover,#15803d)] disabled:opacity-60"
            :disabled="waitingForPayment"
            @click="payNow"
          >
            <i v-if="waitingForPayment" class="bi bi-arrow-repeat animate-spin"></i>
            {{ waitingForPayment ? 'Waiting for payment...' : 'Pay Now' }}
          </button>
          <router-link
            to="/my-bookings"
            class="mt-2 block w-full rounded-xl py-3 text-center font-semibold"
            :class="result.payment_link
              ? 'border border-[var(--portal-primary,#16a34a)] text-[var(--portal-primary,#16a34a)] hover:bg-[var(--portal-primary,#16a34a)] hover:text-white'
              : 'bg-[var(--portal-primary,#16a34a)] text-white hover:bg-[var(--portal-primary-hover,#15803d)]'"
          >
            My Bookings
          </router-link>
        </div>
        </div>
      </div>
    </div>
  </div>
    <!-- Time-slot picker: a modal rather than inline content, so selecting
         a date never changes the height of the card behind it (which was
         stretching/distorting the facility photo panel via flex stretch). -->
    <Teleport to="body">
      <div v-if="slotsModalOpen" class="fixed inset-0 z-40 bg-slate-900/40" @click="cancelSlotsModal"></div>
      <div
        v-if="slotsModalOpen"
        class="fixed inset-0 z-50 flex items-end justify-center p-0 sm:items-center sm:p-4"
        @click.self="cancelSlotsModal"
      >
          <div
            class="flex max-h-[85vh] w-full flex-col overflow-hidden rounded-t-2xl bg-white shadow-2xl sm:max-w-md sm:rounded-2xl"
            role="dialog" aria-modal="true" aria-label="Select a time slot"
          >
            <div class="flex items-center justify-between gap-2 border-b border-slate-900/5 px-5 py-4">
              <div>
                <p class="m-0 text-sm font-semibold text-slate-800">{{ selectedFacilityInfo.facility_name || selectedFacility }}</p>
                <p class="m-0 text-xs text-slate-500">{{ selectedDate }}</p>
              </div>
              <button
                type="button"
                class="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border-0 bg-transparent text-lg text-slate-500 hover:bg-slate-100"
                aria-label="Close" @click="cancelSlotsModal"
              >
                <i class="bi bi-x-lg"></i>
              </button>
            </div>

            <div class="overflow-y-auto p-5">
              <div v-if="loadingSlots" class="py-6 text-center text-slate-400">Loading...</div>
              <template v-else-if="slotsChecked">
                <p v-if="!slots.length" class="mb-0 text-slate-500">No open slots for this facility on this date.</p>
                <template v-else>
                  <p class="mb-3 text-sm text-slate-500">Select one or more slots &mdash; you can pick a different date and add more before checking out.</p>
                  <div class="grid grid-cols-2 gap-2 sm:grid-cols-3">
                    <button
                      v-for="s in slots" :key="s.start_time" type="button"
                      class="rounded-lg border px-2 py-2 text-center text-sm font-semibold"
                      :class="isSlotSelected(s)
                        ? 'text-white shadow-[0_0_0_2px_color-mix(in_srgb,var(--portal-primary,#16a34a)_25%,transparent)]'
                        : 'border-[var(--portal-primary,#16a34a)] text-[var(--portal-primary,#16a34a)] hover:bg-[var(--portal-primary,#16a34a)] hover:text-white'"
                      :style="isSlotSelected(s) ? { backgroundColor: 'var(--portal-primary, #16a34a)', borderColor: 'var(--portal-primary, #16a34a)' } : {}"
                      @click="toggleSlot(s)"
                    >
                      <i v-if="isSlotSelected(s)" class="bi bi-check-circle-fill mr-1"></i>
                      {{ s.start_time }} &ndash; {{ s.end_time }}
                    </button>
                  </div>
                </template>
              </template>
            </div>

            <div class="border-t border-slate-900/5 px-5 py-4">
              <button
                type="button"
                class="border-0 w-full rounded-xl bg-[var(--portal-primary,#16a34a)] py-2.5 font-semibold text-white hover:bg-[var(--portal-primary-hover,#15803d)]"
                @click="confirmSlotsModal"
              >
                {{ cart.length ? 'Done \u00b7 ' + cart.length + ' slot' + (cart.length === 1 ? '' : 's') + ' selected' : 'Done' }}
              </button>
            </div>
          </div>
      </div>
    </Teleport>
</template>

<script>
import { call, hasServerMessage } from '@/api/frappe';
import { useAuthStore } from '@/stores/auth';

// "Remember this browser" for a short window after a guest verifies their
// email - same key/shape as the pre-migration book-facility page (see
// BOOKING_REMEMBER_TOKEN_TTL_SECONDS / issue_booking_remember_token() /
// verify_booking_remember_token() in sports_complex/utils/guest_booking.py)
// so a guest who already verified there stays remembered here too.
const REMEMBER_KEY = 'sc_booking_remember_v1';

function loadRememberedBooking() {
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

export default {
  setup() {
    return { auth: useAuthStore() };
  },
  data() {
    const now = new Date();
    const today = now.toISOString().slice(0, 10);
    const remembered = loadRememberedBooking();
    return {
      facilities: [],
      loadingFacilities: true,
      currencySymbol: (window.portalBoot && window.portalBoot.currency_symbol) || '',
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
      slotsModalOpen: false,
      cartSnapshot: [],
      slots: [],
      cart: [],
      notes: '',
      guestName: '',
      guestEmail: (remembered && remembered.email) || '',
      guestPhone: '',
      guestOtp: '',
      wantsAccount: false,
      accountPassword: '',
      accountResult: null,
      accountSignedIn: false,
      otpSent: false,
      sendingOtp: false,
      otpCountdown: 0,
      otpCountdownTimer: null,
      guestRememberEmail: (remembered && remembered.email) || '',
      guestRememberToken: remembered ? remembered.token : null,
      booking: false,
      result: null,
      paymentPopup: null,
      paymentPollTimer: null,
      waitingForPayment: false,
    };
  },
  computed: {
    canSendOtp() {
      return this.guestName.trim() && /\S+@\S+\.\S+/.test(this.guestEmail);
    },
    guestVerified() {
      if (!this.guestRememberToken || !this.guestRememberEmail) return false;
      if (this.guestRememberEmail !== this.guestEmail.trim().toLowerCase()) return false;
      const expiresAt = parseInt(this.guestRememberToken.split('.')[0], 10);
      return Number.isFinite(expiresAt) && expiresAt * 1000 > Date.now();
    },
    detailsSubmitLabel() {
      if (this.guestVerified) return this.booking ? 'Booking...' : 'Confirm Booking';
      return this.sendingOtp ? 'Sending...' : 'Send Verification Code';
    },
    accountPasswordInvalid() {
      return this.wantsAccount && this.accountPassword.length < 8;
    },
    detailsSubmitDisabled() {
      if (this.accountPasswordInvalid) return true;
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
    // The cart review list groups back-to-back slots on the same day into
    // a single displayed range (09:00-10:00 + 10:00-11:00 -> 09:00-11:00)
    // - the underlying cart stays one entry per hour (that's still what
    // gets booked/priced), this only changes how the list prints.
    groupedCart() {
      const byDate = {};
      this.cart.forEach((item) => {
        if (!byDate[item.booking_date]) byDate[item.booking_date] = [];
        byDate[item.booking_date].push(item);
      });
      const groups = [];
      Object.keys(byDate).sort().forEach((date) => {
        const items = byDate[date].slice().sort((a, b) => a.start_time.localeCompare(b.start_time));
        let current = null;
        items.forEach((item) => {
          if (current && current.end_time === item.start_time) {
            current.end_time = item.end_time;
            current.items.push(item);
          } else {
            current = { booking_date: date, start_time: item.start_time, end_time: item.end_time, items: [item] };
            groups.push(current);
          }
        });
      });
      return groups;
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
  created() {
    this.loadFacilities();
  },
  methods: {
    loadFacilities() {
      this.loadingFacilities = true;
      call('sports_complex.sports_complex.doctype.facility_booking.facility_booking.list_bookable_facilities')
        .then((facilities) => {
          this.facilities = facilities || [];
        })
        .finally(() => {
          this.loadingFacilities = false;
        });
    },
    fmt(amount) {
      return this.currencySymbol + Number(amount || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
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
    // Whether any cart item (already-added slot, from any prior modal
    // session) falls on this calendar day - shown as a green outline so
    // the month view makes it obvious which dates already have picks,
    // not just which one is currently open in the picker.
    dayHasSelection(day) {
      const key = this.dayKey(day);
      return this.cart.some(item => item.booking_date === key);
    },
    dayStyle(day) {
      // Border color and fill are independent: a day can be both the
      // actively-viewed date (green fill) AND already have cart items
      // from an earlier pick (green border) at the same time, so this
      // must not let one override the other.
      const style = {};
      if (this.dayHasSelection(day)) {
        style.borderColor = 'var(--portal-primary, #16a34a)';
      } else if (this.isToday(day)) {
        style.borderColor = 'color-mix(in srgb, var(--portal-primary, #16a34a) 40%, transparent)';
      }
      if (this.isSelected(day)) {
        style.backgroundColor = 'var(--portal-primary, #16a34a)';
      }
      return style;
    },
    selectDay(day) {
      if (this.isPastDay(day)) return;
      this.selectedDate = this.dayKey(day);
      this.checkAvailability();
      this.cartSnapshot = this.cart.map(item => ({ ...item }));
      this.slotsModalOpen = true;
    },
    // X button / backdrop click: discard any slot picks made in this
    // modal session and restore the cart to how it looked when the
    // modal opened.
    cancelSlotsModal() {
      this.cart = this.cartSnapshot.map(item => ({ ...item }));
      this.slotsModalOpen = false;
    },
    // "Done" button: keep whatever's currently selected.
    confirmSlotsModal() {
      this.slotsModalOpen = false;
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
      call(
        'sports_complex.sports_complex.doctype.facility_booking.facility_booking.get_month_availability',
        { sports_facility: this.selectedFacility, year: this.visibleYear, month: this.visibleMonth }
      ).then((availability) => {
        this.monthAvailability = availability || {};
        this.loadingMonth = false;
      }).catch(() => {
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
      this.cart = [];
      this.step = 'grid';
    },
    checkAvailability() {
      this.loadingSlots = true;
      this.slotsChecked = false;
      call(
        'sports_complex.sports_complex.doctype.facility_booking.facility_booking.get_available_slots',
        { sports_facility: this.selectedFacility, date: this.selectedDate }
      ).then((slots) => {
        this.slots = slots || [];
        this.slotsChecked = true;
        this.loadingSlots = false;
      }).catch(() => {
        window.Swal && window.Swal.fire('Error', 'Could not load availability. Please try again.', 'error');
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
    // Same rate * hours math as cartTotal, applied to one grouped review-list
    // row instead of the whole cart - group.start_time/end_time already
    // span its full merged range, so this is exactly what that row costs.
    groupPrice(group) {
      const rate = Number(this.selectedFacilityInfo.hourly_rate || 0);
      return rate * this.slotHours(group);
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
    // Removing a merged range removes every underlying slot it stands for.
    removeGroupFromCart(group) {
      group.items.forEach((item) => this.removeFromCart(item));
    },
    confirmBooking() {
      this.booking = true;
      call(
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
      ).then((result) => {
        this.result = result;
        this.cart = [];
        this.notes = '';
        this.step = 'result';
        this.booking = false;
      }).catch((err) => {
        if (!hasServerMessage(err)) {
          window.Swal && window.Swal.fire('Error', 'Could not create the booking(s). One or more slots may have just been taken - please choose again.', 'error');
        }
        this.booking = false;
      });
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
    handleAccountResult(account) {
      // account is only present when this.wantsAccount was checked (see
      // create_account/account_password above) - absent entirely for a
      // guest who didn't opt in, so this is a no-op for the common case.
      if (!account) return;
      this.accountResult = account;
      if (!account.created) return;
      // A real session cookie, established in the background right here
      // rather than through the auth store's login() (which does a full
      // page navigation - not wanted yet, since the booking confirmation
      // on this same screen still needs to be shown first). By the time
      // the guest clicks through to My Bookings, they're already signed
      // in as the account they just created.
      call('login', { usr: this.guestEmail, pwd: this.accountPassword })
        .then(() => {
          this.accountSignedIn = true;
          // Sync the auth store so the Navbar switches to the signed-in
          // state (name + Sign out) right away - see setLoggedInLocally()'s
          // own comment for why this doesn't happen automatically.
          this.auth.setLoggedInLocally(this.guestEmail, this.guestName);
        })
        .catch(() => {
          // Non-fatal: the account still exists and the booking still
          // succeeded - they can just sign in manually from /portal/login.
        })
        .finally(() => {
          // Don't hold the plaintext password in memory any longer than
          // this one login call needs it for.
          this.accountPassword = '';
        });
    },
    confirmGuestBooking() {
      const usingRememberToken = this.guestVerified;
      this.booking = true;
      call(
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
          create_account: this.wantsAccount ? 1 : 0,
          account_password: this.wantsAccount ? this.accountPassword : null,
        }
      ).then((result) => {
        this.result = result;
        this.rememberGuestVerification(this.guestEmail, result && result.remember_token);
        this.handleAccountResult(result && result.account);
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
          window.Swal && window.Swal.fire('Verification expired', 'Please verify your email again to continue.', 'info');
          return;
        }
        if (!hasServerMessage(err)) {
          window.Swal && window.Swal.fire('Error', 'Could not verify the code or create the booking(s). Please try again.', 'error');
        }
        this.booking = false;
      });
    },
    bookingViewTo(b) {
      return { path: `/booking-confirmation/${b.name}`, query: b.token ? { token: b.token } : {} };
    },
    payNow() {
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
        window.location.href = url;
        return;
      }

      this.paymentPopup = popup;
      this.waitingForPayment = true;
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
          // One last check in case payment actually went through right
          // before the guest closed the tab - only then give up waiting.
          this.refreshPaymentStatus().finally(() => {
            this.waitingForPayment = false;
          });
          return;
        }
        this.refreshPaymentStatus();
      }, 3000);
    },
    refreshPaymentStatus() {
      const primary = this.result && this.result.bookings && this.result.bookings[0];
      if (!primary) return Promise.resolve();
      return call(
        'sports_complex.sports_complex.doctype.facility_booking.facility_booking.get_booking_status',
        { facility_booking: primary.name, token: primary.token }
      ).then((status) => {
        if (!status) return;
        if (status.booking_status === 'Confirmed' || status.payment_status === 'Paid') {
          this.result.booking_status = status.booking_status;
          this.result.payment_link = null;
          this.waitingForPayment = false;
          if (this.paymentPollTimer) {
            clearInterval(this.paymentPollTimer);
            this.paymentPollTimer = null;
          }
          if (this.paymentPopup && !this.paymentPopup.closed) {
            this.paymentPopup.close();
          }
          this.paymentPopup = null;
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
        // check status later via "View Booking".
      });
    },
  },
  beforeUnmount() {
    if (this.paymentPollTimer) clearInterval(this.paymentPollTimer);
    if (this.otpCountdownTimer) clearInterval(this.otpCountdownTimer);
  },
};
</script>
