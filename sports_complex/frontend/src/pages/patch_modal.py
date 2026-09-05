#!/usr/bin/env python3
import re

p = "BookFacility.vue"
content = open(p, encoding="utf-8").read()

old = '''      <div class="flex w-full">
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
        <div class="flex min-w-0 flex-1 flex-col overflow-y-auto">
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

        <!-- Step 2: confirm identity + book -->'''

assert content.count(old) == 1, ("main block", content.count(old))

new = '''      <div class="flex w-full">
        <!-- Column 1: date-picker calendar (was the facility photo) while
             picking a date/slot - Column 2 now shows the time slots for
             whatever date is picked here instead of the calendar itself.
             Falls back to the facility's own photo for the details/result
             steps, where there's no calendar to show. Hidden below md so
             the flow's other column keeps its full width on narrow
             screens. -->
        <div v-if="step === 'browse'" class="max-md:hidden w-3/5 shrink-0 overflow-y-auto border-r border-slate-900/5 bg-slate-50 p-6">
          <div class="mb-2 flex items-center justify-between">
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
        <div
          v-else-if="selectedFacilityInfo.image"
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

        <!-- Column 2: the existing step-by-step flow. Step 1 now shows the
             time slots for the date picked in Column 1's calendar, instead
             of hosting the calendar itself. -->
        <div class="flex min-w-0 flex-1 flex-col overflow-y-auto">
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

        <!-- Step 1: time slots for the selected date -->
        <div v-if="step === 'browse'" class="p-6">
          <p class="mb-1 flex items-center gap-2 rounded-lg px-4 py-3 font-semibold text-slate-800" style="background: color-mix(in srgb, var(--portal-primary, #16a34a) 8%, transparent);">
            <i class="bi bi-geo-alt"></i>
            {{ selectedFacilityInfo.facility_name || selectedFacility }}
            <span v-if="selectedFacilityInfo.surface_type" class="font-normal text-slate-500">&middot; {{ selectedFacilityInfo.surface_type }}</span>
          </p>
          <p class="mb-4 text-sm font-semibold text-slate-800">{{ selectedDate }}</p>

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

        <!-- Step 2: confirm identity + book -->'''

content = content.replace(old, new)
open(p, "w", encoding="utf-8").write(content)
print("ok2")
