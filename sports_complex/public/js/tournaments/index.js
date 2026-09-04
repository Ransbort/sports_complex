const { createApp } = Vue;

// See book-facility/index.js's own copy of this same helper for the full
// explanation - the "server already explained itself" flag lives at
// err.responseJSON._server_messages on frappe.call()'s rejected promise.
function hasServerMessage(err) {
  if (!err) return false;
  if (err._server_messages) return true;
  if (err.responseJSON && err.responseJSON._server_messages) return true;
  return false;
}

// Same "remember this browser after a verified OTP" pattern as
// book-facility/book-coach's own REMEMBER_KEYs - a separate localStorage
// key so a Register for a Tournament remember-token is never confused
// with either of theirs.
const REMEMBER_KEY = 'sc_tournament_registration_remember_v1';

function loadRemembered() {
  try {
    const raw = localStorage.getItem(REMEMBER_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (parsed && parsed.email && parsed.token) return parsed;
  } catch (e) {
    // Storage unavailable - fall back to the normal email/OTP form.
  }
  return null;
}

function saveRemembered(email, token) {
  try {
    localStorage.setItem(REMEMBER_KEY, JSON.stringify({ email: (email || '').trim().toLowerCase(), token }));
  } catch (e) {
    // Nothing to do if storage isn't available.
  }
}

createApp({
  delimiters: ['[[', ']]'],
  data() {
    const now = new Date();
    const today = now.toISOString().slice(0, 10);
    const remembered = loadRemembered();
    return {
      tournaments: window.tournaments || [],
      isGuest: !!window.isGuest,
      currencySymbol: window.currencySymbol || '',
      step: 'grid', // 'grid' -> 'detail' -> 'result'
      today,
      selectedTournament: {},
      teams: [],
      loadingTeams: false,
      selectedTeam: '',
      playerName: '',
      dateOfBirth: '',
      guardianName: '',
      guardianRelationship: '',
      guardianContact: '',
      guardianEmail: '',
      consentGiven: false,
      email: remembered ? remembered.email : '',
      guestName: '',
      otp: '',
      otpSent: false,
      sendingOtp: false,
      guestRememberToken: remembered ? remembered.token : '',
      submitting: false,
      errorMessage: '',
      resultMessage: '',
      paymentLink: '',
    };
  },
  computed: {
    // Mirrors Player Registration.set_age_and_minor_flag() client-side -
    // see book-coach/index.js's own copy of this computed property for
    // why (the server is still the one that actually enforces it).
    isMinor() {
      if (!this.dateOfBirth) return false;
      const dob = new Date(this.dateOfBirth);
      if (isNaN(dob.getTime())) return false;
      const now = new Date();
      let age = now.getFullYear() - dob.getFullYear();
      const m = now.getMonth() - dob.getMonth();
      if (m < 0 || (m === 0 && now.getDate() < dob.getDate())) age--;
      return age < 18;
    },
    isTeamPath() {
      return this.selectedTournament.registration_type === 'Team';
    },
    canSubmit() {
      if (this.isTeamPath) {
        if (!this.selectedTeam) return false;
      } else {
        if (!this.playerName || !this.dateOfBirth) return false;
        if (this.isMinor && !(this.guardianName && this.guardianContact && this.consentGiven)) return false;
      }
      if (this.isGuest) {
        if (!this.email || !this.guestName) return false;
        if (!this.guestRememberToken && !this.otpSent) return false;
        if (!this.guestRememberToken && this.otpSent && !this.otp) return false;
      }
      return true;
    },
  },
  methods: {
    fmt(amount) {
      return this.currencySymbol + Number(amount || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    },
    isFull(t) {
      return t.spots_remaining != null && t.spots_remaining <= 0;
    },
    dateRange(t) {
      if (!t || !t.start_date) return '';
      if (!t.end_date || t.end_date === t.start_date) return t.start_date;
      return t.start_date + ' - ' + t.end_date;
    },
    pickTournament(t) {
      if (this.isFull(t)) return;
      this.selectedTournament = t;
      this.step = 'detail';
      this.selectedTeam = '';
      this.playerName = '';
      this.dateOfBirth = '';
      this.otp = '';
      this.otpSent = false;
      this.errorMessage = '';
      this.teams = [];
      if (t.registration_type === 'Team') {
        this.loadTeams();
      }
    },
    backToGrid() {
      this.step = 'grid';
    },
    loadTeams() {
      this.loadingTeams = true;
      frappe.call(
        'sports_complex.sports_complex.doctype.tournament_registration.tournament_registration.get_tournament_teams',
        { tournament: this.selectedTournament.name }
      ).then((r) => {
        this.teams = r.message || [];
      }).finally(() => {
        this.loadingTeams = false;
      });
    },
    sendOtp() {
      if (!this.email) return;
      this.sendingOtp = true;
      frappe.call('sports_complex.utils.guest_booking.send_booking_otp', { email: this.email })
        .then(() => {
          this.otpSent = true;
        })
        .catch((err) => {
          if (!hasServerMessage(err)) {
            Swal.fire({ icon: 'error', title: 'Could not send code', text: 'Please try again.' });
          }
        })
        .finally(() => {
          this.sendingOtp = false;
        });
    },
    submitRegistration() {
      if (!this.canSubmit || this.submitting) return;
      this.submitting = true;
      this.errorMessage = '';

      const payload = { tournament: this.selectedTournament.name };
      if (this.isTeamPath) {
        payload.team = this.selectedTeam;
      } else {
        payload.full_name = this.playerName;
        payload.date_of_birth = this.dateOfBirth;
        payload.guardian_name = this.guardianName;
        payload.guardian_relationship = this.guardianRelationship;
        payload.guardian_contact = this.guardianContact;
        payload.guardian_email = this.guardianEmail;
        payload.consent_given = this.consentGiven ? 1 : 0;
      }

      let method = 'sports_complex.sports_complex.doctype.tournament_registration.tournament_registration.create_tournament_registration';
      if (this.isGuest) {
        method = 'sports_complex.sports_complex.doctype.tournament_registration.tournament_registration.create_guest_tournament_registration';
        payload.email = this.email;
        payload.full_name = payload.full_name || this.guestName;
        payload.otp = this.otp;
        payload.remember_token = this.guestRememberToken;
      }

      frappe.call(method, payload).then((r) => {
        const msg = r.message || {};
        if (this.isGuest && msg.remember_token) {
          saveRemembered(this.email, msg.remember_token);
          this.guestRememberToken = msg.remember_token;
        }
        this.resultMessage = 'Your entry into ' + this.selectedTournament.tournament_name +
          (msg.status === 'Waitlisted' ? ' has been waitlisted - the tournament is currently full.' : ' is confirmed.');
        this.paymentLink = msg.payment_link || '';
        this.step = 'result';
      }).catch((err) => {
        if (!hasServerMessage(err)) {
          this.errorMessage = 'Could not submit this registration - please try again.';
        }
      }).finally(() => {
        this.submitting = false;
      });
    },
  },
}).mount('#app');
