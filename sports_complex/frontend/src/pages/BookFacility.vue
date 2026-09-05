<template>
  <div class="h-full flex flex-col overflow-y-auto lg:overflow-hidden">

    <!-- Step 0: browse all bookable facilities - a fullscreen, two-panel
         view of one facility at a time on the left (colored panel: name/
         price/status up top, the facility's own photo filling whatever
         space is left, a visually separated "Book Now" bar along the very
         bottom - not just another button inline with the rest), facts + a
         thumbnail strip of every other facility on the right - rather
         than the flat card grid this used to be. See browseIndex/
         browsePrev()/browseNext()/browseGoTo() below. "Book Now" still
         goes through the same pickFacility() used by the old grid, so
         steps 1-3 (date/slot pick, identity, result) are untouched. -->
    <div class="flex h-full flex-col gap-2 p-4 lg:overflow-hidden lg:grid! lg:grid-cols-3 lg:grid-rows-[minmax(0,1fr)]">
      <p v-if="loadingFacilities" class="w-full py-16 text-center text-slate-400">Loading facilities...</p>
      <p v-else-if="!facilities.length" class="w-full py-16 text-center text-slate-400">No facilities are open for booking right now.</p>

      <template v-else>
        <!-- Left: rotating hero for the facility currently in view -->
        <div class="relative flex h-[clamp(14rem,52vh,28rem)] shrink-0 flex-col overflow-hidden rounded-t-2xl lg:col-span-1 lg:h-full">
          <!-- Image row - its own section, sized to fill everything
               above the Book Now bar. The photo and gradient are
               absolute WITHIN THIS WRAPPER only (not the whole panel),
               so they can never show through behind/around the Book Now
               bar below - a real two-row layout, not an overlap. -->
          <div class="relative flex min-h-0 flex-1 flex-col overflow-hidden">
            <div
              class="absolute inset-0 bg-slate-800 bg-cover bg-center"
              :style="browseFacility.image ? { backgroundImage: 'url(' + browseFacility.image + ')' } : {}"
            ></div>
            <div class="absolute inset-0 bg-gradient-to-b from-black/60 via-black/10 to-black/25"></div>

            <router-link to="/" class="relative z-10 flex items-center gap-2 px-4 pt-4 lg:px-6 lg:pt-6">
              <span class="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-white/90 shadow-sm">
                <img v-if="auth.appLogo" :src="auth.appLogo" :alt="auth.appName" class="h-5 w-5 object-contain rounded" />
                <i v-else class="bi bi-trophy-fill text-[var(--portal-primary,#16a34a)]"></i>
              </span>
              <span class="font-extrabold text-white">{{ auth.appName }}</span>
            </router-link>

            <div class="relative z-10 flex min-h-0 flex-1 flex-col justify-end gap-3 p-6 pt-16 lg:p-8 lg:pt-20">
              <div>
                <p v-if="browseFacility.facility_type" class="mb-1 text-xs font-bold uppercase tracking-wide text-white/70">{{ browseFacility.facility_type }}</p>
                <h1 class="mt-0 text-[clamp(1.5rem,5vw,2.25rem)] font-extrabold leading-tight text-white">{{ browseFacility.facility_name }}</h1>
              </div>
              <div class="flex flex-wrap items-center gap-2.5">
                <span class="flex items-baseline gap-1.5">
                  <span class="text-[clamp(1.125rem,4vw,1.25rem)] font-extrabold text-white">{{ fmt(browseFacility.hourly_rate) }}</span>
                  <span class="text-sm font-medium text-white/65">/ hour</span>
                </span>
                <span
                  class="w-fit rounded-full px-3 py-1 text-xs font-semibold text-white"
                  :style="{ backgroundColor: browseFacility.open_slots_today ? 'rgba(255,255,255,0.22)' : 'rgba(0,0,0,0.22)' }"
                >
                  {{ browseFacility.open_slots_today ? browseFacility.open_slots_today + ' open today' : 'Fully booked today' }}
                </span>
              </div>

              <div class="flex items-center gap-1.5">
                <button
                  v-for="(f, i) in facilities" :key="'dot-' + f.name" type="button" :aria-label="'View ' + f.facility_name"
                  class="h-1.5 rounded-full border-0 p-0 transition-all"
                  :class="i === browseIndex ? 'w-5 bg-white' : 'w-1.5 bg-white/40'"
                  @click="browseGoTo(i)"
                ></button>
              </div>
            </div>
          </div>

          <!-- Separated primary action - its own row, not inline with the
               rest of the panel's content (matches the reference: a
               distinct bottom strip, not just another button in the flow). -->
          <button
            type="button"
            class="group relative z-10 flex shrink-0 items-center justify-between rounded-b-2xl border-x-0 border-b-0 border-t-2 border-dashed border-white bg-[var(--portal-primary,#16a34a)] px-7 py-8 text-left transition-colors duration-300 hover:bg-[var(--portal-primary-hover,#15803d)] lg:px-9"
            @click="pickFacility(browseFacility)"
          >
            <!-- Ticket-stub notches - half-circles "punched" out of the
                 panel's edges right on the dashed seam, half hidden by
                 the panel's own overflow-hidden. -->
            <span class="absolute -left-2.5 top-0 z-20 h-5 w-5 -translate-y-1/2 rounded-full bg-slate-50"></span>
            <span class="absolute -right-2.5 top-0 z-20 h-5 w-5 -translate-y-1/2 rounded-full bg-slate-50"></span>
            <span class="text-[clamp(1.375rem,4.5vw,1.625rem)] font-extrabold text-white">Book Now</span>
            <!-- "Shooting arrow" hover: the resting arrow slides out to the
                 top-right while an identical arrow slides in from the
                 bottom-left to take its place, clipped by the wrapper. -->
            <span class="relative inline-block h-[clamp(1.25rem,4.5vw,1.5rem)] w-[clamp(1.25rem,4.5vw,1.5rem)] shrink-0 overflow-hidden">
              <i class="bi bi-arrow-up-right absolute inset-0 text-[clamp(1.25rem,4.5vw,1.5rem)] text-white transition-transform duration-300 ease-out group-hover:translate-x-full group-hover:-translate-y-full"></i>
              <i class="bi bi-arrow-up-right absolute inset-0 -translate-x-full translate-y-full text-[clamp(1.25rem,4.5vw,1.5rem)] text-white transition-transform duration-300 ease-out group-hover:translate-x-0 group-hover:translate-y-0"></i>
            </span>
          </button>
        </div>

        <!-- Right: facts for the facility in view + a thumbnail strip to
             jump straight to any other one -->
        <div class="flex min-h-0 flex-1 flex-col overflow-y-auto lg:col-span-2">
          <div class="flex items-center justify-between border-b border-slate-900/5 px-6 py-4 lg:px-10">
            <p class="m-0 text-sm font-semibold text-slate-500">{{ browseIndex + 1 }} of {{ facilities.length }} facilities</p>
            <div class="flex items-center gap-2">
              <router-link
                to="/my-bookings"
                class="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white p-2 text-sm font-semibold text-slate-700 no-underline hover:bg-slate-50 hover:no-underline"
              >
                <i class="bi bi-calendar2-check"></i> My Bookings
              </router-link>
              <button
                type="button"
                class="flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200 bg-white p-0 text-slate-700 hover:bg-slate-50"
                aria-label="Open menu"
                aria-haspopup="true"
                :aria-expanded="ui.menuOpen"
                @click="ui.openMenu()"
              >
                <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="h-5 w-5">
                  <path d="M4 5h16"/>
                  <path d="M4 12h16"/>
                  <path d="M4 19h16"/>
                </svg>
              </button>
            </div>
          </div>

          <div class="flex min-h-0 flex-1 flex-col justify-between gap-6 p-6! pb-0! lg:p-10! lg:pb-0!">
            <div class="shrink-0">
              <p class="mb-1 text-xs font-bold uppercase tracking-wide text-[var(--portal-primary,#16a34a)]">Browse Facilities</p>
              <h2 class="m-0 text-[clamp(1.75rem,4.5vw,2.25rem)] font-extrabold leading-tight text-slate-900">Find your court, pick a time, play.</h2>
              <p class="mt-1 text-slate-500">Browse facilities and reserve a time slot.</p>
            </div>

            <div class="grid shrink-0 grid-cols-3 gap-3">
              <div class="rounded-2xl border border-slate-900/5 bg-white p-3.5 shadow-[0_4px_20px_rgba(15,23,42,0.06)]">
                <p class="mb-0.5 text-xs font-semibold text-slate-400">Type</p>
                <p class="text-sm font-bold text-slate-800">{{ browseFacility.facility_type || '—' }}</p>
              </div>
              <div class="rounded-2xl border border-slate-900/5 bg-white p-3.5 shadow-[0_4px_20px_rgba(15,23,42,0.06)]">
                <p class="mb-0.5 text-xs font-semibold text-slate-400">Rate</p>
                <p class="text-sm font-bold text-slate-800">{{ fmt(browseFacility.hourly_rate) }}/hr</p>
              </div>
              <div class="rounded-2xl border border-slate-900/5 bg-white p-3.5 shadow-[0_4px_20px_rgba(15,23,42,0.06)]">
                <p class="mb-0.5 text-xs font-semibold text-slate-400">Today</p>
                <p class="text-sm font-bold text-slate-800">{{ browseFacility.open_slots_today ? browseFacility.open_slots_today + ' open' : 'Fully booked' }}</p>
              </div>
            </div>

            <div class="shrink-0">
              <p class="mb-3 text-xs font-bold uppercase tracking-wide text-slate-800">How Booking Works</p>
              <div class="flex flex-col gap-3.5">
                <div class="flex items-start gap-3">
                  <span class="flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[var(--portal-primary,#16a34a)]" style="background-color: color-mix(in srgb, var(--portal-primary, #16a34a) 14%, white);">
                    <i class="bi bi-calendar2-check text-sm"></i>
                  </span>
                  <div>
                    <p class="mb-0! text-sm font-bold text-slate-800">Pick a date and slot</p>
                    <p class="text-sm text-slate-500">See what's open today or later this month.</p>
                  </div>
                </div>
                <div class="flex items-start gap-3">
                  <span class="flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[var(--portal-primary,#16a34a)]" style="background-color: color-mix(in srgb, var(--portal-primary, #16a34a) 14%, white);">
                    <i class="bi bi-check-lg text-sm"></i>
                  </span>
                  <div>
                    <p class="mb-0! text-sm font-bold text-slate-800">Confirm your details</p>
                    <p class="text-sm text-slate-500">Review the slots you've selected and add a note if needed.</p>
                  </div>
                </div>
                <div class="flex items-start gap-3">
                  <span class="flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[var(--portal-primary,#16a34a)]" style="background-color: color-mix(in srgb, var(--portal-primary, #16a34a) 14%, white);">
                    <i class="bi bi-lock-fill text-sm"></i>
                  </span>
                  <div>
                    <p class="mb-0! text-sm font-bold text-slate-800">Pay securely with Paystack</p>
                    <p class="text-sm text-slate-500">Your booking is confirmed the moment payment clears.</p>
                  </div>
                </div>
              </div>
            </div>

            <div class="shrink-0">
              <div class="mb-3 flex items-center justify-between">
                <p class="m-0 text-xs font-bold uppercase tracking-wide text-slate-800">All facilities</p>
                <div class="flex items-center gap-2">
                  <button
                    type="button" aria-label="Previous facility"
                    class="flex h-8 w-8 items-center justify-center rounded-full border border-slate-200 bg-white p-0 text-slate-700 hover:bg-slate-50"
                    @click="browsePrev"
                  ><i class="bi bi-chevron-left"></i></button>
                  <button
                    type="button" aria-label="Next facility"
                    class="flex h-8 w-8 items-center justify-center rounded-full border border-slate-200 bg-white p-0 text-slate-700 hover:bg-slate-50"
                    @click="browseNext"
                  ><i class="bi bi-chevron-right"></i></button>
                </div>
              </div>
              <div
                ref="facilityStrip"
                class="hide-scrollbar flex touch-pan-y select-none gap-3 overflow-x-auto p-1"
                :class="stripDragActive ? 'cursor-grabbing' : 'cursor-grab'"
                @pointerdown="onStripPointerDown"
                @pointermove="onStripPointerMove"
                @pointerup="onStripPointerUp"
                @pointerleave="onStripPointerUp"
                @pointercancel="onStripPointerUp"
              >
                <button
                  v-for="(f, i) in facilities" :key="f.name" type="button" :aria-label="f.facility_name"
                  class="relative aspect-[4/3] w-24 shrink-0 overflow-hidden rounded-2xl border-0 bg-slate-100 bg-cover bg-center p-0 lg:w-56"
                  :style="f.image ? { backgroundImage: 'url(' + f.image + ')' } : {}"
                  :class="i === browseIndex ? 'ring-2 ring-[var(--portal-primary,#16a34a)]' : 'ring-1 ring-slate-900/10'"
                  @click="browseGoTo(i)"
                >
                  <span v-if="i !== browseIndex" class="absolute inset-0 bg-slate-900/30"></span>
                </button>
              </div>
            </div>
          </div>
        </div>
      </template>
    </div>
    </div>

    <!-- Steps 1-3: date/slot pick, identity, result - a popup over the
         grid (Book Now opens this modal) instead of replacing the page,
         so "All facilities" stays visible, dimmed, behind it. -->
    <Teleport to="body">
      <div v-if="step !== 'grid'" class="fixed inset-0 z-40 bg-slate-900/40" @click="backToGrid"></div>
      <div
        v-if="step !== 'grid'"
        class="fixed inset-0 z-50 flex items-end justify-center p-0 sm:items-center sm:p-4"
        @click.self="backToGrid"
      >
      <div
        class="relative flex h-[55vh] max-h-[35rem] w-full flex-col overflow-hidden rounded-t-2xl bg-white shadow-2xl max-md:h-[85vh] max-md:max-h-none sm:max-w-4xl sm:rounded-2xl"
        role="dialog" aria-modal="true" aria-label="Book a Facility"
      >
        <button
          type="button"
          class="absolute right-3 top-3 z-10 flex h-8 w-8 items-center justify-center rounded-lg border-0 bg-white/90 text-lg text-slate-500 shadow-sm hover:bg-slate-100"
          aria-label="Close" @click="backToGrid"
        >
          <i class="bi bi-x-lg"></i>
        </button>
      <div class="flex w-full min-h-0 flex-1 max-md:relative max-md:overflow-hidden">
        <!-- Column 1: date-picker calendar (was the facility photo) while
             picking a date/slot - Column 2 now shows the time slots for
             whatever date is picked here instead of the calendar itself.
             Falls back to the facility's own photo for the details/result
             steps, where there's no calendar to show. Hidden below md so
             the flow's other column keeps its full width on narrow
             screens. -->
        <div
          v-if="step === 'browse'"
          class="flex w-full flex-col overflow-y-auto bg-slate-50 p-6 max-md:absolute max-md:inset-0 max-md:z-10 max-md:transition-transform max-md:duration-300 max-md:ease-in-out md:w-3/5 md:shrink-0 md:rounded-tr-xl md:rounded-br-xl md:border-r md:border-slate-900/5"
          :class="mobileBrowseView === 'calendar' ? '' : 'max-md:pointer-events-none max-md:-translate-x-full'"
        >
          <div class="mb-4 shrink-0 flex items-center justify-between gap-2 border-b border-slate-900/5 pb-4">
            <div class="flex items-center gap-2 font-bold text-slate-800">
              <i class="bi bi-calendar2-check text-[var(--portal-primary,#16a34a)]"></i>
              <span>Book a Facility</span>
            </div>
            <p class="m-0 flex items-center gap-1.5 text-xs text-slate-500">
              <span class="inline-block h-1.5 w-1.5 rounded-full" style="background: var(--portal-primary, #16a34a);"></span> open
              <span class="inline-block h-1.5 w-1.5 rounded-full bg-slate-300"></span> fully booked
            </p>
          </div>
          <div class="mb-4 shrink-0 flex items-center justify-between gap-2 rounded-lg bg-white px-4 py-3 font-semibold text-slate-800">
            <p class="m-0 flex min-w-0 items-center gap-2 truncate">
              <i class="bi bi-geo-alt shrink-0"></i>
              <span class="truncate">{{ selectedFacilityInfo.facility_name || selectedFacility }}</span>
              <span v-if="selectedFacilityInfo.surface_type" class="shrink-0 font-normal text-slate-500">&middot; {{ selectedFacilityInfo.surface_type }}</span>
            </p>
            <span class="shrink-0 text-sm font-semibold text-slate-500">{{ selectedDate }}</span>
          </div>
          <div class="mb-2 shrink-0 flex items-center justify-between">
            <button
              type="button"
              class="flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-700 disabled:opacity-40"
              :disabled="isPrevMonthDisabled" @click="prevMonth"
            ><i class="bi bi-chevron-left"></i></button>
            <span class="text-sm font-semibold text-slate-800">{{ monthLabel }}</span>
            <button
              type="button"
              class="flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-700"
              @click="nextMonth"
            ><i class="bi bi-chevron-right"></i></button>
          </div>
          <div class="mb-2 shrink-0 grid grid-cols-7 gap-1.5 text-center text-xs font-semibold uppercase text-slate-400">
            <span v-for="d in dowLabels" :key="d">{{ d }}</span>
          </div>
          <div class="grid flex-1 auto-rows-fr grid-cols-7 gap-1.5 text-center">
            <span v-for="n in leadingBlanks" :key="'b' + n"></span>
            <button
              v-for="day in daysInMonth" :key="day" type="button"
              class="relative flex items-center justify-center rounded-lg text-sm font-semibold text-slate-800 disabled:cursor-default disabled:text-slate-300"
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
          <p class="mt-2 mb-0 h-5 shrink-0 text-center text-sm text-slate-400">{{ loadingMonth ? 'Loading availability...' : '' }}</p>
        </div>
        <div
          v-else-if="step === 'result' && selectedFacilityInfo.image"
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
        <div v-else-if="step === 'result'" class="max-md:hidden! flex w-3/5 shrink-0 items-center justify-center bg-slate-100">
          <i class="bi bi-image text-4xl text-slate-300"></i>
        </div>

        <!-- Column 2: the existing step-by-step flow. Step 1 now shows the
             time slots for the date picked in Column 1's calendar, instead
             of hosting the calendar itself. -->
        <div class="flex min-w-0 flex-1 flex-col min-h-0">

        <!-- Step 1: time slots for the selected date. Only the slots
             grid itself scrolls (flex-1 min-h-0 overflow-y-auto below) so
             the pill/date stay put and the card's height never changes
             with the slot count. -->
        <div v-if="step === 'browse'" class="flex min-h-0 flex-1 flex-col p-6">
          <div class="mb-3 shrink-0 flex items-center gap-2 md:hidden!">
            <button
              type="button"
              class="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-700"
              aria-label="Back to calendar" @click="mobileBrowseView = 'calendar'"
            ><i class="bi bi-chevron-left"></i></button>
            <span class="truncate text-sm font-semibold text-slate-800">{{ selectedDate }}</span>
          </div>
          <div v-if="loadingSlots" class="shrink-0 py-6 text-center text-slate-400">Loading...</div>
          <template v-else-if="slotsChecked">
            <p v-if="!slots.length" class="shrink-0 mb-0 text-slate-500">No open slots for this facility on this date.</p>
            <template v-else>
              <!-- Helper line sits outside the scroll area (shrink-0) so
                   it stays put at the top while only the slots grid below
                   it scrolls. -->
              <p class="shrink-0 mb-3 text-sm text-slate-500">Select one or more slots &mdash; you can pick a different date and add more before checking out.</p>
              <div class="min-h-0 flex-1 overflow-y-auto [scrollbar-width:thin] [scrollbar-color:color-mix(in_srgb,var(--portal-primary,#16a34a)_35%,transparent)_transparent] [&::-webkit-scrollbar]:w-2.5 [&::-webkit-scrollbar-track]:bg-transparent [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-[color-mix(in_srgb,var(--portal-primary,#16a34a)_35%,transparent)] [&::-webkit-scrollbar-thumb]:hover:bg-[color-mix(in_srgb,var(--portal-primary,#16a34a)_55%,transparent)]">
                <div class="flex flex-col gap-1.5 p-1">
                  <button
                    v-for="s in slots" :key="s.start_time" type="button"
                    class="rounded-lg border px-4 py-2.5 text-center text-base font-semibold whitespace-nowrap"
                    :class="isSlotSelected(s)
                      ? 'text-white shadow-[0_0_0_2px_color-mix(in_srgb,var(--portal-primary,#16a34a)_25%,transparent)]'
                      : 'border-[var(--portal-primary,#16a34a)] text-[var(--portal-primary,#16a34a)] hover:bg-[var(--portal-primary,#16a34a)] hover:text-white'"
                    :style="isSlotSelected(s) ? { backgroundColor: 'var(--portal-primary, #16a34a)', borderColor: 'var(--portal-primary, #16a34a)' } : {}"
                    @click="toggleSlot(s)"
                  >
                    <i v-if="isSlotSelected(s)" class="bi bi-check-circle-fill mr-1"></i>
                    {{ fmtTime(s.start_time) }}&ndash;{{ fmtTime(s.end_time) }}
                  </button>
                </div>
              </div>
            </template>
          </template>

          <div v-if="cart.length" class="mt-4 shrink-0 flex items-center justify-between gap-4 rounded-xl px-4 py-3.5 font-semibold text-slate-800" style="background: color-mix(in srgb, var(--portal-primary, #16a34a) 8%, transparent);">
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
        <div v-else-if="step === 'details'" class="flex min-h-0 flex-1 flex-col">
          <!-- Two-column layout: the booking summary (facility, slots,
               total) stays on the left as a fixed reference while the
               user fills in their details on the right - a familiar
               checkout-style split rather than one long stacked column.
               Collapses back to a single column on narrow screens. -->
          <div class="grid min-h-0 flex-1 max-md:overflow-y-auto md:grid-cols-2">
            <!-- Column 1: booking summary - styled to match the calendar
                 card treatment from the browse step (bg-slate-50 card with
                 a bordered header bar and a white pill row), with the same
                 right-hand divider the calendar uses to separate itself
                 from the next column. Flex-col + h-full so the total can
                 be pinned to the bottom. -->
            <div class="flex h-full flex-col rounded-xl border-r border-slate-900/5 bg-slate-50 p-6">
              <div class="sticky top-0 z-10 mb-4 flex items-center justify-between gap-2 border-b border-slate-900/5 bg-slate-50 pb-4 pr-14 pt-1 text-[1rem] font-bold text-slate-800 max-md:-mx-6 max-md:px-6 md:static md:top-auto md:z-auto md:mx-0 md:bg-transparent md:px-0! md:pt-0 md:pr-6!">
                <span class="flex items-center gap-2">
                  <i class="bi bi-calendar2-check text-[var(--portal-primary,#16a34a)]"></i>
                  Booking Summary
                </span>
                <button type="button" class="shrink-0 border-0 bg-transparent p-0 text-[0.875rem]! font-semibold text-slate-500 hover:text-slate-700" @click="step = 'browse'; mobileBrowseView = 'slots'">&larr; Add more slots</button>
              </div>
              <p class="mb-4 flex items-center gap-2 rounded-lg bg-white px-4 py-3 font-semibold text-slate-800">
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
              <div class="mt-auto flex items-center justify-between gap-2 rounded-xl px-4 py-3.5 font-semibold text-slate-800" style="background: color-mix(in srgb, var(--portal-primary, #16a34a) 8%, transparent);">
                <span>Total</span>
                <span class="text-lg font-bold">{{ fmt(cartTotal) }}</span>
              </div>
            </div>

            <!-- Column 2: user entry - fills the full width and height
                 of its grid cell, and uses a white background to match the
                 time-slot section from the browse step (Column 1 mirrors
                 the calendar's bg-slate-50 instead). -->
            <div class="flex h-full flex-col rounded-xl bg-white p-6">
              <template v-if="auth.isLoggedIn">
                <div class="mb-4">
                  <label class="mb-1 block text-sm font-medium text-slate-500">Notes (optional)</label>
                  <textarea
                    v-model="notes" rows="2" maxlength="500" placeholder="Anything we should know about this booking?"
                    class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-[var(--portal-primary,#16a34a)] focus:outline-none focus:ring-1 focus:ring-[var(--portal-primary,#16a34a)]"
                  ></textarea>
                </div>
                <button
                  class="mt-auto border-0 flex w-full items-center justify-center gap-2 rounded-xl bg-[var(--portal-primary,#16a34a)] py-3 font-semibold text-white hover:bg-[var(--portal-primary-hover,#15803d)] disabled:opacity-60"
                  :disabled="booking || !cart.length" @click="confirmBooking"
                >
                  <i v-if="booking" class="bi bi-arrow-repeat animate-spin"></i>
                  {{ booking ? 'Booking...' : 'Confirm Booking' }}
                </button>
              </template>

              <template v-else>
                <form v-if="!otpSent" class="flex flex-1 flex-col gap-4" @submit.prevent="proceedFromDetails">
                  <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
                    <div>
                      <label class="mb-1 block text-sm font-medium text-slate-500">Full Name</label>
                      <input type="text" v-model="guestName" required class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-[var(--portal-primary,#16a34a)] focus:outline-none focus:ring-1 focus:ring-[var(--portal-primary,#16a34a)]">
                    </div>
                    <div>
                      <label class="mb-1 block text-sm font-medium text-slate-500">Email</label>
                      <input type="email" v-model="guestEmail" required class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-[var(--portal-primary,#16a34a)] focus:outline-none focus:ring-1 focus:ring-[var(--portal-primary,#16a34a)]">
                    </div>
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
                    <label class="mb-0 flex items-start gap-2 text-sm font-medium text-slate-700">
                      <input type="checkbox" v-model="wantsAccount" class="mt-0.5 h-4 w-4 rounded border-slate-300 text-[var(--portal-primary,#16a34a)] focus:ring-[var(--portal-primary,#16a34a)]">
                      Create account (Optional)
                    </label>
                    <input
                      v-if="wantsAccount" type="password" v-model="accountPassword" required minlength="8"
                      placeholder="Choose a password (min. 8 characters)" autocomplete="new-password"
                      class="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-[var(--portal-primary,#16a34a)] focus:outline-none focus:ring-1 focus:ring-[var(--portal-primary,#16a34a)]"
                    >
                  </div>
                  <p v-if="guestVerified" class="flex flex-wrap items-center gap-1.5 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2.5 text-sm text-emerald-800">
                    <i class="bi bi-patch-check-fill text-emerald-600"></i>
                    Verified as <strong>{{ guestEmail }}</strong> - no code needed right now.
                    <button type="button" class="ml-auto border-0 bg-transparent p-0 font-semibold text-[var(--portal-primary,#16a34a)]" @click="forgetGuestVerification">Not you?</button>
                  </p>
                  <button
                    type="submit"
                    class="mt-auto border-0 flex w-full items-center justify-center rounded-xl bg-[var(--portal-primary,#16a34a)] py-3.5 font-semibold text-white hover:bg-[var(--portal-primary-hover,#15803d)] disabled:opacity-60"
                    :disabled="detailsSubmitDisabled"
                  >
                    {{ detailsSubmitLabel }}
                  </button>
                </form>
                <form v-else class="flex flex-1 flex-col gap-4" @submit.prevent="confirmGuestBooking">
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
                    class="mt-auto border-0 flex w-full items-center justify-center gap-2 rounded-xl bg-[var(--portal-primary,#16a34a)] py-3 font-semibold text-white hover:bg-[var(--portal-primary-hover,#15803d)] disabled:opacity-60"
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
            </div>
          </div>
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
    </Teleport>
</template>

<script>
import { call, hasServerMessage } from '@/api/frappe';
import { useAuthStore } from '@/stores/auth';
import { useUiStore } from '@/stores/ui';

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
    return { auth: useAuthStore(), ui: useUiStore() };
  },
  data() {
    const now = new Date();
    const today = now.toISOString().slice(0, 10);
    const remembered = loadRememberedBooking();
    return {
      facilities: [],
      loadingFacilities: true,
      browseIndex: 0, // which facility the step==='grid' hero/thumbnail-strip view is showing
      stripDragActive: false, // true while a pointer-drag is scrolling the facility strip
      stripDragMoved: false, // true once a drag has moved enough to not count as a click
      stripDragStartX: 0,
      stripDragStartScrollLeft: 0,
      currencySymbol: (window.portalBoot && window.portalBoot.currency_symbol) || '',
      step: 'grid', // 'grid' -> 'browse' -> 'details' -> 'result'
      mobileBrowseView: 'calendar', // 'calendar' | 'slots' - which pane is active on mobile within the browse step
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
    browseFacility() {
      return this.facilities[this.browseIndex] || {};
    },
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
    browsePrev() {
      if (!this.facilities.length) return;
      this.browseIndex = (this.browseIndex - 1 + this.facilities.length) % this.facilities.length;
      this.$nextTick(() => this.scrollActiveThumbIntoView());
    },
    browseNext() {
      if (!this.facilities.length) return;
      this.browseIndex = (this.browseIndex + 1) % this.facilities.length;
      this.$nextTick(() => this.scrollActiveThumbIntoView());
    },
    browseGoTo(i) {
      if (this.stripDragMoved) return; // this "click" is actually the end of a drag
      this.browseIndex = i;
      this.$nextTick(() => this.scrollActiveThumbIntoView());
    },
    scrollActiveThumbIntoView() {
      const strip = this.$refs.facilityStrip;
      const active = strip && strip.children[this.browseIndex];
      if (active) active.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' });
    },
    onStripPointerDown(e) {
      this.stripDragActive = true;
      this.stripDragMoved = false;
      this.stripDragStartX = e.clientX;
      this.stripDragStartScrollLeft = this.$refs.facilityStrip.scrollLeft;
    },
    onStripPointerMove(e) {
      if (!this.stripDragActive) return;
      const dx = e.clientX - this.stripDragStartX;
      if (Math.abs(dx) > 4) this.stripDragMoved = true;
      this.$refs.facilityStrip.scrollLeft = this.stripDragStartScrollLeft - dx;
    },
    onStripPointerUp() {
      this.stripDragActive = false;
    },
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
    // Slot times come back as "08:00:00" - drop the seconds so they read
    // as "08:00" and fit on one line in the slot buttons.
    fmtTime(t) {
      return t ? String(t).slice(0, 5) : t;
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
      this.mobileBrowseView = 'slots';
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
      this.mobileBrowseView = 'calendar';
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
    this.ui.navbarHidden = false;
  },
  watch: {
    // Every step on this page draws its own top bar: the fullscreen
    // grid step has its own logo (top-left, over the hero photo) and
    // its own hamburger button (beside "My Bookings"), and the
    // browse/details/result steps run inside the booking modal, which
    // already has its own close control - the global Navbar's top bar
    // would just be a second, redundant header sitting above the
    // overlay in either case, so keep it hidden for the whole page and
    // only restore it (in beforeUnmount) once we navigate away.
    step: {
      immediate: true,
      handler() {
        this.ui.navbarHidden = true;
      },
    },
  },
};
</script>
