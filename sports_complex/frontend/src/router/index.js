import { createRouter, createWebHistory } from 'vue-router';
import Home from '@/pages/Home.vue';
import Login from '@/pages/Login.vue';
import BookCoach from '@/pages/BookCoach.vue';
import BookFacility from '@/pages/BookFacility.vue';
import MyBookings from '@/pages/MyBookings.vue';
import BookingConfirmation from '@/pages/BookingConfirmation.vue';

// No auth guard on any of these: guest booking (emailed OTP, no account)
// is a deliberate, permanent option across this whole app - not a
// fallback for before you sign in - so nothing here should ever force a
// visitor through /login first. Signing in only unlocks a nicer
// experience (booking history in one place, not retyping your name every
// time), never a gate.
const routes = [
  { path: '/', name: 'home', component: Home, meta: { title: 'Sports Complex' } },
  { path: '/login', name: 'login', component: Login, meta: { title: 'Sign In' } },
  { path: '/book-coach', name: 'book-coach', component: BookCoach, meta: { title: 'Book a Coach' } },
  { path: '/book-facility', name: 'book-facility', component: BookFacility, meta: { title: 'Book a Facility' } },
  { path: '/my-bookings', name: 'my-bookings', component: MyBookings, meta: { title: 'My Bookings' } },
  {
    path: '/booking-confirmation/:name',
    name: 'booking-confirmation',
    component: BookingConfirmation,
    meta: { title: 'Booking Confirmation' },
  },
];

const router = createRouter({
  // Base matches website_route_rules' catch-all in hooks.py - any
  // /portal/<path:app_path> request server-side resolves to this same
  // shell page, which is what lets a hard reload/deep link on e.g.
  // /portal/book-coach work at all instead of 404ing before Vue Router
  // ever gets a chance to take over client-side.
  history: createWebHistory('/portal'),
  routes,
  scrollBehavior() {
    return { top: 0 };
  },
});

export default router;
