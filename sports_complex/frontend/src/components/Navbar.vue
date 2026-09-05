<template>
  <!-- Plain white top bar - just the brand and a hamburger button. All
       navigation (page links + sign in/out) lives in the slide-out
       sidebar below rather than inline here, at every screen size - see
       the user's explicit request for a hamburger + sidebar nav rather
       than a responsive-only mobile menu. No sticky positioning needed:
       App.vue's fixed h-screen shell means this bar structurally can't
       scroll out of view. Styled to match the "Book a Facility" header
       bar inside the booking modal (white background, hairline bottom
       border, px-6/py-5 padding) so the two read as one consistent
       header treatment across the site. -->
  <nav v-if="!ui.navbarHidden" class="shrink-0 z-20 border-b border-slate-900/5 bg-white px-6 py-5">
    <div class="mx-auto flex max-w-6xl items-center justify-between">
      <router-link to="/" class="flex items-center gap-2.5 shrink-0" @click="closeMenu">
        <span
          class="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg"
          style="background-color: color-mix(in srgb, var(--portal-primary, #16a34a) 14%, white);"
        >
          <img v-if="auth.appLogo" :src="auth.appLogo" :alt="auth.appName" class="h-5 w-5 object-contain rounded" />
          <i v-else class="bi bi-trophy-fill text-[var(--portal-primary,#16a34a)]"></i>
        </span>
        <span class="font-extrabold leading-tight text-slate-900">{{ auth.appName }}</span>
      </router-link>

      <button
        type="button"
        class="flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200 bg-white p-0 text-slate-700 shadow-sm hover:bg-slate-50"
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
  </nav>

  <!-- Backdrop + sidebar are teleported to <body> rather than left inline,
       so their fixed positioning can never be undermined by an ancestor
       picking up a CSS transform later (a transformed ancestor turns
       position:fixed into "fixed to that ancestor" instead of the
       viewport) - cheap insurance for a full-screen overlay like this. -->
  <Teleport to="body">
    <Transition name="sc-fade">
      <div
        v-if="ui.menuOpen"
        class="fixed inset-0 z-30 bg-slate-900/40"
        @click="closeMenu"
      ></div>
    </Transition>

    <Transition name="sc-slide">
      <aside
        v-if="ui.menuOpen"
        class="fixed inset-y-0 right-0 z-40 flex w-72 max-w-[85vw] flex-col bg-white shadow-2xl"
        role="dialog"
        aria-modal="true"
        aria-label="Navigation"
      >
        <div class="flex items-center justify-between border-b border-slate-200 px-4 py-3">
          <span class="flex items-center gap-2 font-extrabold text-slate-900">
            <img v-if="auth.appLogo" :src="auth.appLogo" :alt="auth.appName" class="h-6 w-6 object-contain rounded" />
            <i v-else class="bi bi-trophy-fill text-[var(--portal-primary,#16a34a)]"></i>
            {{ auth.appName }}
          </span>
          <button
            type="button"
            class="flex h-8 w-8 items-center justify-center rounded-lg border-0 bg-transparent p-0 text-[var(--portal-primary,#16a34a)] hover:bg-slate-100"
            aria-label="Close menu"
            @click="closeMenu"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="h-5 w-5">
              <path d="M18 6 6 18"/>
              <path d="m6 6 12 12"/>
            </svg>
          </button>
        </div>

        <nav class="flex flex-1 flex-col gap-0.5 overflow-y-auto px-3 py-4 text-sm font-semibold text-slate-600">
          <router-link
            to="/book-coach" class="rounded-lg px-3 py-2.5 hover:bg-slate-50 hover:text-[var(--portal-primary,#16a34a)]"
            active-class="bg-slate-50 text-[var(--portal-primary,#16a34a)]" @click="closeMenu"
          >
            <i class="bi bi-person-badge mr-2"></i>Book a Coach
          </router-link>
          <router-link
            to="/book-facility" class="rounded-lg px-3 py-2.5 hover:bg-slate-50 hover:text-[var(--portal-primary,#16a34a)]"
            active-class="bg-slate-50 text-[var(--portal-primary,#16a34a)]" @click="closeMenu"
          >
            <i class="bi bi-calendar2-check mr-2"></i>Book a Facility
          </router-link>
          <!-- Not yet migrated into this app - see frontend/README.md - so
               these are plain links to the existing standalone pages. -->
          <a href="/book-player" class="rounded-lg px-3 py-2.5 hover:bg-slate-50 hover:text-[var(--portal-primary,#16a34a)]">
            <i class="bi bi-person-check mr-2"></i>Book a Player
          </a>
          <a href="/tournaments" class="rounded-lg px-3 py-2.5 hover:bg-slate-50 hover:text-[var(--portal-primary,#16a34a)]">
            <i class="bi bi-trophy mr-2"></i>Tournaments
          </a>
          <router-link
            to="/my-bookings" class="rounded-lg px-3 py-2.5 hover:bg-slate-50 hover:text-[var(--portal-primary,#16a34a)]"
            active-class="bg-slate-50 text-[var(--portal-primary,#16a34a)]" @click="closeMenu"
          >
            <i class="bi bi-list-check mr-2"></i>My Bookings
          </router-link>
        </nav>

        <div class="border-t border-slate-200 px-4 py-3.5">
          <template v-if="auth.isLoggedIn">
            <div class="mb-2.5 truncate text-sm text-slate-500">{{ auth.fullName || auth.user }}</div>
            <button
              type="button"
              class="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm font-semibold text-slate-600 hover:bg-slate-50"
              @click="handleSignOut"
            >
              Sign out
            </button>
          </template>
          <router-link
            v-else to="/login"
            class="portal-signin-btn block rounded-lg px-3 py-2 text-center text-sm font-semibold text-white shadow-sm"
            @click="closeMenu"
          >
            Sign in
          </router-link>
        </div>
      </aside>
    </Transition>
  </Teleport>
</template>

<script setup>
import { onBeforeUnmount, watch } from 'vue';
import { useRoute } from 'vue-router';
import { useAuthStore } from '@/stores/auth';
import { useUiStore } from '@/stores/ui';

const auth = useAuthStore();
const ui = useUiStore();
const route = useRoute();

function closeMenu() {
  ui.closeMenu();
}

function handleSignOut() {
  closeMenu();
  auth.logout();
}

// Auto-close on route change (an in-app router-link navigation already
// closes the sidebar via its own @click, but this also covers back/
// forward-button navigation, which fires no click at all) and on Escape,
// and stop the page underneath from scrolling while the sidebar is open.
watch(() => route.fullPath, closeMenu);

function handleKeydown(e) {
  if (e.key === 'Escape') closeMenu();
}
watch(() => ui.menuOpen, (open) => {
  document.documentElement.classList.toggle('sc-menu-open', open);
  if (open) {
    window.addEventListener('keydown', handleKeydown);
  } else {
    window.removeEventListener('keydown', handleKeydown);
  }
});
onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleKeydown);
  document.documentElement.classList.remove('sc-menu-open');
});
</script>

<style scoped>
/* Same "scoped CSS class reading the --portal-primary custom property"
   approach Home.vue's .portal-action-primary already uses successfully -
   a plain Tailwind bg-[var(--portal-primary,...)] arbitrary-value class
   on this exact button was rendering with no background at all (white
   text on white = invisible, the bug that was reported), so this sets
   the color through an ordinary CSS rule instead of relying on that
   arbitrary-value class generation. */
.portal-signin-btn {
  background-color: var(--portal-primary, #16a34a);
}
.portal-signin-btn:hover {
  background-color: var(--portal-primary-hover, #15803d);
}

.sc-fade-enter-active,
.sc-fade-leave-active {
  transition: opacity 0.2s ease;
}
.sc-fade-enter-from,
.sc-fade-leave-to {
  opacity: 0;
}

.sc-slide-enter-active,
.sc-slide-leave-active {
  transition: transform 0.25s ease;
}
.sc-slide-enter-from,
.sc-slide-leave-to {
  transform: translateX(100%);
}
</style>

<style>
/* Unscoped (global) on purpose - toggled on <html> itself while the
   sidebar is open, so it needs to reach outside this component's own
   scoped styles to affect the shared app shell. */
html.sc-menu-open,
html.sc-menu-open body {
  overflow: hidden;
}
</style>
