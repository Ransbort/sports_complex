import { defineStore } from 'pinia';

// Shared UI-chrome state that needs to be driven from outside Navbar.vue
// itself - e.g. BookFacility.vue's fullscreen "grid" step hides the
// top bar entirely and puts its own hamburger button in the right panel
// instead, but that button still needs to open the exact same slide-out
// sidebar Navbar.vue owns. Keeping menuOpen here (rather than as a local
// ref inside Navbar.vue) lets any page toggle it without Navbar.vue
// needing to expose anything imperative.
export const useUiStore = defineStore('ui', {
  state: () => ({
    navbarHidden: false,
    menuOpen: false,
  }),
  actions: {
    openMenu() {
      this.menuOpen = true;
    },
    closeMenu() {
      this.menuOpen = false;
    },
  },
});
