// Thin wrapper around the global `frappe` object that every page on this
// site already gets from templates/web.html (see e.g. book-coach/index.js's
// own copy of these same helpers, pre-migration). frappe.call() already
// handles CSRF tokens, session cookies, and the plumbing for whitelisted
// method calls - the SPA doesn't need its own HTTP client or auth-token
// scheme on top of Frappe's normal cookie session. Kept in one place now
// instead of copy-pasted per page (that drift is the whole reason this
// app exists - see frontend/README.md).

export function call(method, args = {}) {
  // Promise.resolve() here assimilates frappe.call()'s jQuery-style
  // Deferred into a real native Promise before anything chains off of
  // it. That matters because jQuery's own Promise/Deferred objects
  // implement .then()/.catch() but never .finally() - every page in
  // this app that did call(...).then(...).finally(...) was one bad
  // request away from a hard "TypeError: ...finally is not a function"
  // (this broke Book a Facility's own facility list on load). Wrapping
  // it once here, in the one shared place every page's frappe.call()
  // goes through, fixes it everywhere instead of auditing every call
  // site for which promise methods it happens to chain.
  return Promise.resolve(window.frappe.call(method, args)).then((r) => r && r.message);
}

// Same jqXHR-vs-responseJSON gotcha every legacy page's own copy of this
// documents: frappe.call()'s .catch() hands back the raw jqXHR, and the
// field that says "the server already explained itself" (so don't show a
// second, generic error on top of Frappe's own popup) lives at
// err.responseJSON._server_messages, not a bare err._server_messages.
export function hasServerMessage(err) {
  if (!err) return false;
  if (err._server_messages) return true;
  if (err.responseJSON && err.responseJSON._server_messages) return true;
  return false;
}

// Best-effort extraction of the first human-readable message a failed
// call's frappe.throw() attached, for inline display (a login form, an
// error line under a button) instead of relying on frappe.call()'s own
// popup dialog.
export function firstServerMessage(err) {
  try {
    const raw = (err && err._server_messages) || (err && err.responseJSON && err.responseJSON._server_messages);
    if (!raw) return '';
    const messages = JSON.parse(raw);
    const first = JSON.parse(messages[0]);
    return first.message || '';
  } catch (e) {
    return '';
  }
}
