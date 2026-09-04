# Sports Complex Portal (Vue frontend)

The public-facing booking site is being migrated, page by page, from the
old approach (one hand-rolled Vue app per `www/<page>/` + `public/js/<page>/`,
each mounted onto its own server-rendered Jinja page) into a single Vue 3
SPA with client-side routing - this directory.

## Why

With Book a Facility, Book a Coach, Book a Player, and Tournaments each
having their own copy-pasted Vue app, shared logic (guest OTP flow,
currency formatting, server-error handling) was drifting slightly between
copies, and there was nowhere for a real signed-in account to live across
pages. This app fixes both: one shared API/auth layer, one router, pages
added incrementally.

## Status

Migrated into this app: sign-in (email + password, real Frappe session -
see `src/stores/auth.js`), Book a Coach, Book a Facility (including its
month calendar and multi-slot cart - the most involved of the four
booking flows, so the other two should be more straightforward).

Still on the old per-page approach for now: Book a Player, Tournaments,
My Bookings. Their existing `www/`/`public/js/` pages are untouched and
still work - the Home page and Navbar just link out to them until they're
migrated too. Migrate one at a time by copying `src/pages/BookFacility.vue`
or `BookCoach.vue`'s shape (fetch its own data on mount via
`src/api/frappe.js`'s `call()`, no server-injected JSON) and adding a
route in `src/router/index.js`.

## Styling

Tailwind CSS v4 (`@tailwindcss/vite`, see `vite.config.js` and
`src/style.css`) - utility classes only, Preflight is deliberately not
imported (see `src/style.css`'s own comment) since this page also loads
the site's Bootstrap-based web theme via `templates/web.html`, and
Preflight's element resets would fight that rather than layer on top of
it cleanly. The one exception is `Home.vue`'s `.portal-action` card,
which is easier to read as a few real CSS rules (shared by all five
cards, primary vs. secondary variants) than the same thing spelled out
in Tailwind's `@apply` or repeated inline on every card - normal
`<style scoped>`, no different from any other Vue app.

Every themed color (buttons, borders, badges, hover states) reads
`var(--portal-primary)` / `var(--portal-primary-hover)`, set once as CSS
custom properties on `:root` in `www/portal/index.html` from Sports
Complex Setup's own Theme Color (see `sports_complex/theme.py`) - the
same site-wide color every legacy page already themes off of, just one
shared variable name here instead of a different prefix per page. Change
the color in Setup, not in this app.

## Dev

    cd frontend
    npm install
    npm run dev

`vite dev` serves this app standalone at http://localhost:8090 using the
fake `window.portalBoot` in `index.html` - it can render the UI but can't
successfully call the backend (no real Frappe session/CSRF token) unless
you're also running this against a real site's dev server with API
requests proxied there. For a real end-to-end test, `npm run build` and
load the actual site's `/portal` page instead.

## Build

    npm run build

Outputs to `../public/portal/assets/{main.js,main.css}` (fixed filenames,
no hashing - see vite.config.js). No separate deploy step: these are
static files under this app's own `public/`, served the same way as
everything under `public/js/` already is. Rebuild and commit the output
whenever `src/` changes - there's no CI build step for this app.
