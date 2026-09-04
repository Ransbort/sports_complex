<template>
  <div class="flex min-h-full items-center justify-center p-6 md:p-10">
    <div class="w-full max-w-sm md:max-w-4xl">
      <div class="overflow-hidden rounded-xl border-[1px] border-slate-200 bg-white p-0 shadow-sm">
        <div class="grid p-0 md:grid-cols-2">
          <!-- Form column -->
          <div class="p-6 md:p-8">
            <!-- Already signed in -->
            <div v-if="auth.isLoggedIn" class="flex h-full flex-col items-center justify-center gap-4 py-8 text-center">
              <i class="bi bi-check-circle-fill text-4xl text-[var(--portal-primary,#16a34a)]"></i>
              <div>
                <h1 class="text-2xl font-bold text-slate-900">Welcome back</h1>
                <p class="mt-1 text-slate-500">You're already signed in as {{ auth.fullName || auth.user }}.</p>
              </div>
              <router-link
                to="/"
                class="inline-flex h-9 items-center justify-center gap-2 whitespace-nowrap rounded-md border-0 bg-[var(--portal-primary,#16a34a)] px-4 py-2 text-sm font-medium text-white shadow-xs transition-all hover:bg-[var(--portal-primary-hover,#15803d)]"
              >
                Go to home
              </router-link>
            </div>

            <!-- Sign in -->
            <form v-else-if="mode === 'signin'" class="flex flex-col gap-6" @submit.prevent="submit">
              <div class="flex flex-col items-center gap-2 text-center">
                <h1 class="text-2xl font-bold text-slate-900">Welcome back</h1>
                <p class="text-balance text-slate-500">Sign in to your Sports Complex account</p>
              </div>

              <div class="flex w-full flex-col gap-3">
                <label for="email" class="text-sm font-medium leading-none text-slate-900">Email</label>
                <input
                  id="email"
                  type="email"
                  v-model="usr"
                  required
                  autofocus
                  placeholder="m@example.com"
                  class="flex h-9 w-full min-w-0 rounded-md border-[1px] border-slate-200 bg-transparent px-3 py-1 text-sm text-slate-900 shadow-xs outline-none transition-[color,box-shadow] placeholder:text-slate-400 focus-visible:border-[var(--portal-primary,#16a34a)] focus-visible:ring-[3px] focus-visible:ring-[var(--portal-primary,#16a34a)]/50 disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50"
                >
              </div>

              <div class="flex w-full flex-col gap-3">
                <div class="flex items-center">
                  <label for="password" class="text-sm font-medium leading-none text-slate-900">Password</label>
                  <button
                    type="button"
                    class="ml-auto border-0 bg-transparent p-0 text-sm text-[var(--portal-primary,#16a34a)] underline-offset-2 hover:underline"
                    @click="openReset"
                  >
                    Forgot your password?
                  </button>
                </div>
                <input
                  id="password"
                  type="password"
                  v-model="pwd"
                  required
                  class="flex h-9 w-full min-w-0 rounded-md border-[1px] border-slate-200 bg-transparent px-3 py-1 text-sm text-slate-900 shadow-xs outline-none transition-[color,box-shadow] focus-visible:border-[var(--portal-primary,#16a34a)] focus-visible:ring-[3px] focus-visible:ring-[var(--portal-primary,#16a34a)]/50 disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50"
                >
              </div>

              <div class="flex w-full flex-col gap-3">
                <button
                  type="submit"
                  :disabled="auth.loggingIn"
                  class="inline-flex h-9 w-full items-center justify-center gap-2 whitespace-nowrap rounded-md border-0 bg-[var(--portal-primary,#16a34a)] px-4 py-2 text-sm font-medium text-white shadow-xs transition-all hover:bg-[var(--portal-primary-hover,#15803d)] disabled:pointer-events-none disabled:opacity-50"
                  style="border-radius: 6px;"
                >
                  {{ auth.loggingIn ? 'Signing in...' : 'Login' }}
                </button>
              </div>
              <p v-if="auth.loginError" class="-mt-3 text-sm text-red-600">{{ auth.loginError }}</p>

              <p class="text-center text-sm leading-normal text-slate-500">
                No account yet? Booking as a guest doesn't need one -
                <router-link to="/book-facility" class="font-medium text-[var(--portal-primary,#16a34a)] underline-offset-2 hover:underline">start a booking</router-link>
                and verify your email instead.
            </p>
            </form>

            <!-- Forgot password -->
            <form v-else class="flex flex-col gap-6" @submit.prevent="submitReset">
              <div class="flex flex-col items-center gap-2 text-center">
                <h1 class="text-2xl font-bold text-slate-900">Reset password</h1>
                <p class="text-balance text-slate-500">Enter your email and we'll send you a link to get back in.</p>
              </div>

              <div class="flex w-full flex-col gap-3">
                <label for="reset-email" class="text-sm font-medium leading-none text-slate-900">Email</label>
                <input
                  id="reset-email"
                  type="email"
                  v-model="resetEmail"
                  required
                  autofocus
                  placeholder="m@example.com"
                  class="flex h-9 w-full min-w-0 rounded-md border-[1px] border-slate-200 bg-transparent px-3 py-1 text-sm text-slate-900 shadow-xs outline-none transition-[color,box-shadow] placeholder:text-slate-400 focus-visible:border-[var(--portal-primary,#16a34a)] focus-visible:ring-[3px] focus-visible:ring-[var(--portal-primary,#16a34a)]/50 disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50"
                >
              </div>

              <div class="flex w-full flex-col gap-3">
                <button
                  type="submit"
                  :disabled="resetSending || resetSent"
                  class="inline-flex h-9 w-full items-center justify-center gap-2 whitespace-nowrap rounded-md border-0 bg-[var(--portal-primary,#16a34a)] px-4 py-2 text-sm font-medium text-white shadow-xs transition-all hover:bg-[var(--portal-primary-hover,#15803d)] disabled:pointer-events-none disabled:opacity-50"
                  style="border-radius: 6px;"
                >
                  {{ resetSending ? 'Sending...' : (resetSent ? 'Link sent' : 'Send reset link') }}
                </button>
              </div>

              <p v-if="resetSent" class="-mt-3 flex items-center gap-1.5 text-sm text-emerald-700">
                <i class="bi bi-check-circle-fill"></i>
                If an account exists for that email, a reset link is on its way - check your inbox.
              </p>

              <button
                type="button"
                class="mx-auto border-0 bg-transparent p-0 text-sm font-medium text-slate-500 hover:text-slate-700"
                @click="backToSignIn"
              >
                &larr; Back to sign in
              </button>
            </form>
          </div>

          <!-- Brand panel -->
          <div
            class="relative hidden items-center justify-center p-8 md:!flex"
            style="background: var(--portal-primary, #16a34a);"
          >
            <div class="flex flex-col items-center gap-4 text-center text-white">
              <div class="flex h-20 w-20 items-center justify-center rounded-2xl bg-white/15 p-3">
                <img v-if="auth.appLogo" :src="auth.appLogo" alt="Sports Complex" class="h-full w-full object-contain" />
                <i v-else class="bi bi-trophy-fill text-4xl"></i>
              </div>
              <div>
                <p class="text-lg font-bold">Sports Complex</p>
                <p class="mt-1 text-sm text-white/80">Book facilities, coaches and tournaments in one place.</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue';
import { useAuthStore } from '@/stores/auth';
import { call } from '@/api/frappe';

const auth = useAuthStore();
const usr = ref('');
const pwd = ref('');

const mode = ref('signin'); // 'signin' | 'reset'
const resetEmail = ref('');
const resetSending = ref(false);
const resetSent = ref(false);

function submit() {
  auth.login(usr.value, pwd.value, '/portal');
}

function openReset() {
  // Carry over whatever they'd already typed as the sign-in email, so
  // they're not retyping it - but never the password field, which has
  // no business surviving into a totally different flow.
  resetEmail.value = usr.value;
  resetSent.value = false;
  mode.value = 'reset';
}

function backToSignIn() {
  mode.value = 'signin';
  resetSent.value = false;
}

function submitReset() {
  resetSending.value = true;
  // frappe.core.doctype.user.user.reset_password is core Frappe's own
  // "forgot password" endpoint - the exact one the standard /login page's
  // own "Forgot Password" link calls. It emails a signed reset link
  // (Frappe's built-in /update-password page handles the rest) - there's
  // no custom reset-token/email plumbing to build here.
  //
  // The confirmation banner below is shown the same way whether this
  // succeeds, the account doesn't exist, or the request fails outright -
  // deliberately not distinguishing "no such account" from "sent", so
  // this form can't be used to probe which emails have accounts.
  call('frappe.core.doctype.user.user.reset_password', { user: resetEmail.value })
    .catch(() => {})
    .finally(() => {
      resetSending.value = false;
      resetSent.value = true;
    });
}
</script>
