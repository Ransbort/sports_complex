import { defineStore } from 'pinia';
import { call, firstServerMessage } from '@/api/frappe';

// Real Frappe session login/logout - "login" and "logout" are special
// whitelisted method names Frappe's own core login page calls the exact
// same way (POST usr/pwd, server sets/clears the sid session cookie).
// There's no client-side token to store here; window.portalBoot (read
// below) is what tells this store whether the current request is signed
// in, recomputed server-side on every page load - see
// www/portal/index.py.
export const useAuthStore = defineStore('auth', {
  state: () => {
    const boot = window.portalBoot || {};
    return {
      isGuest: boot.is_guest !== false,
      user: boot.user || 'Guest',
      fullName: boot.full_name || '',
      appLogo: boot.app_logo || '',
      appName: boot.app_name || 'Sports Complex',
      loggingIn: false,
      loginError: '',
    };
  },
  getters: {
    isLoggedIn: (state) => !state.isGuest,
  },
  actions: {
    async login(usr, pwd, redirectTo) {
      this.loggingIn = true;
      this.loginError = '';
      try {
        await call('login', { usr, pwd });
        // Full navigation rather than patching this store's state in
        // place: the next request re-renders www/portal/index.html,
        // which recomputes window.portalBoot from frappe.session.user
        // server-side (the same is_guest pattern every other page in
        // this app already uses) and gives frappe.call() a CSRF token
        // that actually matches the new session.
        window.location.href = redirectTo || '/portal';
      } catch (err) {
        this.loginError = firstServerMessage(err) || 'Could not sign in - check your email and password.';
      } finally {
        this.loggingIn = false;
      }
    },
    async logout() {
      try {
        await call('logout');
      } catch (e) {
        // Best-effort - redirect regardless so the UI never gets stuck on
        // a logout button that silently failed.
      }
      window.location.href = '/portal';
    },
    // Called right after BookFacility.vue's inline "create an account while
    // booking" flow signs the new user in with an AJAX call('login', ...)
    // (not the login() action above, which does a full navigation). That
    // AJAX login sets a real session cookie, but this store's isGuest was
    // only ever computed once, at store-creation, from window.portalBoot -
    // it has no way to notice a session change that happened without a
    // page load. Without this, the Navbar kept showing "Sign in" (and no
    // way to sign out) even though the visitor now has a valid session,
    // until they happened to trigger a full page navigation. This patches
    // the store's state in place so the Navbar reflects reality immediately.
    setLoggedInLocally(user, fullName) {
      this.isGuest = false;
      this.user = user;
      this.fullName = fullName || '';
    },
  },
});
