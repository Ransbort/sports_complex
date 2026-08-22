// Fallback for hiding the site's automatic "Login" nav link - see
// sports_complex.css's matching rule and comment in this same folder for
// why this app hides it site-wide. Loaded via hooks.py's web_include_js
// (public site pages only - never the Desk).
//
// Deliberately narrow: only ever touches an <a> whose href resolves to
// exactly the /login path (not a broad text search for the word "Login",
// which could catch something unrelated elsewhere on the site) and only
// ever hides it - never removes it from the DOM or alters anything else -
// so the worst case if a theme's markup doesn't match is that nothing
// happens, not that something breaks.
(function () {
  function hideLoginLink() {
    document.querySelectorAll('a[href]').forEach(function (a) {
      var path;
      try {
        path = new URL(a.getAttribute("href"), window.location.origin).pathname;
      } catch (e) {
        return;
      }
      if (path === "/login") {
        var li = a.closest("li") || a;
        li.style.display = "none";
      }
    });
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", hideLoginLink);
  } else {
    hideLoginLink();
  }
})();
