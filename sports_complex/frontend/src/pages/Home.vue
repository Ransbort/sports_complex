<template>
  <div
    class="relative flex h-full items-center justify-center overflow-y-auto px-6 py-6"
    style="background: radial-gradient(circle at top, color-mix(in srgb, var(--portal-primary, #16a34a) 8%, transparent), transparent 60%);"
  >
    <div class="w-full max-w-2xl text-center">
      <div
        class="mx-auto mb-3 flex h-14 w-14 items-center justify-center rounded-full overflow-hidden"
        :class="{ 'bg-white shadow-sm': auth.appLogo }"
        :style="auth.appLogo ? '' : 'background: color-mix(in srgb, var(--portal-primary, #16a34a) 12%, transparent);'"
      >
        <img v-if="auth.appLogo" :src="auth.appLogo" alt="Sports Complex" class="h-full w-full object-contain p-2" />
        <i v-else class="bi bi-trophy-fill text-2xl text-[var(--portal-primary,#16a34a)]"></i>
      </div>

      <h1 class="text-2xl font-extrabold text-slate-800 sm:text-3xl">
        Welcome{{ auth.isLoggedIn ? ', ' + (auth.fullName || auth.user) : '' }}
      </h1>
      <p class="mx-auto mt-1 max-w-md text-sm text-slate-500" v-if="!auth.isLoggedIn">
        Browse and book below as a guest, or
        <router-link to="/login" class="font-semibold text-[var(--portal-primary,#16a34a)]">sign in</router-link>
        to keep your bookings in one place.
      </p>

      <div class="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-2">
        <router-link to="/book-facility" class="portal-action portal-action-primary">
          <i class="bi bi-calendar2-check"></i>
          <span class="portal-action-title">Book a Facility</span>
          <span class="portal-action-desc">Browse facilities and reserve a time slot</span>
        </router-link>
        <router-link to="/book-coach" class="portal-action portal-action-secondary">
          <i class="bi bi-person-badge"></i>
          <span class="portal-action-title">Book a Coach</span>
          <span class="portal-action-desc">Book a one-on-one session with a coach</span>
        </router-link>
        <a href="/book-player" class="portal-action portal-action-secondary">
          <i class="bi bi-person-circle"></i>
          <span class="portal-action-title">Book a Player</span>
          <span class="portal-action-desc">Book a one-on-one session with a player</span>
        </a>
        <a href="/tournaments" class="portal-action portal-action-secondary">
          <i class="bi bi-trophy"></i>
          <span class="portal-action-title">Register for a Tournament</span>
          <span class="portal-action-desc">Enter as a team or an individual player</span>
        </a>
        <router-link to="/my-bookings" class="portal-action portal-action-secondary sm:col-span-2">
          <i class="bi bi-list-check"></i>
          <span class="portal-action-title">My Bookings</span>
          <span class="portal-action-desc">View, pay for, or cancel a booking</span>
        </router-link>
      </div>

      <ul class="mt-4 flex flex-wrap items-center justify-center gap-x-5 gap-y-1 text-xs font-medium text-slate-500">
        <li class="flex items-center gap-1.5"><i class="bi bi-lightning-charge-fill text-[var(--portal-primary,#16a34a)]"></i> Instant confirmation</li>
        <li class="flex items-center gap-1.5"><i class="bi bi-credit-card-fill text-[var(--portal-primary,#16a34a)]"></i> Secure online payment</li>
        <li class="flex items-center gap-1.5"><i class="bi bi-person-check-fill text-[var(--portal-primary,#16a34a)]"></i> No account needed to book</li>
      </ul>
    </div>
  </div>
</template>

<script setup>
import { useAuthStore } from '@/stores/auth';
const auth = useAuthStore();
</script>

<style scoped>
/* Same visual language as the www/facilities/index.html landing page own
   .sc-action - one shared component class here instead of one-off
   utility soup per card, since all five cards share the exact same
   shape and only the "primary vs secondary" look differs. Padding and
   font sizes here are tuned tighter than a typical landing page, since
   this whole screen has to fit inside one viewport (see the App shell,
   which sets a fixed h-screen with no page-level scrolling) on top of a
   full 5-card grid, so the vertical rhythm throughout is deliberately
   compact rather than the airier spacing a normally-scrolling page
   would use. */
.portal-action {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.2rem;
  padding: 1.1rem 1.25rem;
  border-radius: 1rem;
  text-decoration: none;
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}
.portal-action:hover {
  transform: translateY(-3px);
}
.portal-action i {
  font-size: 1.4rem;
  margin-bottom: 0.2rem;
}
.portal-action-title {
  font-weight: 700;
  font-size: 0.95rem;
}
.portal-action-desc {
  font-size: 0.75rem;
  font-weight: 400;
}
.portal-action-primary {
  background-color: var(--portal-primary, #16a34a);
  color: #fff;
  box-shadow: 0 10px 28px color-mix(in srgb, var(--portal-primary, #16a34a) 30%, transparent);
}
.portal-action-primary:hover {
  background-color: var(--portal-primary-hover, #15803d);
  color: #fff;
}
.portal-action-primary .portal-action-desc {
  color: rgba(255, 255, 255, 0.85);
}
.portal-action-secondary {
  background-color: #fff;
  color: #1f2937;
  border: 1px solid rgba(15, 23, 42, 0.08);
  box-shadow: 0 4px 20px rgba(15, 23, 42, 0.06);
}
.portal-action-secondary i {
  color: var(--portal-primary, #16a34a);
}
.portal-action-secondary:hover {
  color: #1f2937;
  border-color: color-mix(in srgb, var(--portal-primary, #16a34a) 30%, transparent);
}
.portal-action-secondary .portal-action-desc {
  color: #6b7280;
}
</style>
