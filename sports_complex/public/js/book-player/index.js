const { createApp } = Vue;

// See book-facility/index.js's own copy of this same helper for the full
// explanation - frappe.call()'s .catch() hands back the raw jqXHR, and
// the field that says "the server already explained itself" lives at
// err.responseJSON._server_messages, not a bare err._server_messages.
function hasServerMessage(err) {
  if (!err) return false;
  if (err._server_messages) return true;
  if (err.responseJSON && err.responseJSON._server_messages) return true;
  return false;
}

// Same "remember this browser after a verified OTP" pattern as book-
// coach's own REMEMBER_KEY - a separate localStorage key so a Book a
// Player remember-token is never confused with either of the other two
// guest booking flows.
const REMEMBER_KEY = 'sc_player_booking_remember_v1';

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
      players: window.players || [],
      isGuest: !!window.isGuest,
      currencySymbol: window.currencySymbol || '',
      step: 'grid', // 'grid' -> 'detail' -> 'result'
      today,
      selectedPlayer: {},
      selectedDate: '',
      slots: [],
      loadingSlots: false,
      selectedSlot: null,
      email: remembered ? remembered.email : '',
      otp: '',
      otpSent: false,
      sendingOtp: false,
      guestRememberToken: remembered ? remembered.token : '',
      participantName: '',
      dateOfBirth: '',
      guardianName: '',
      guardianRelationship: '',
      guardianContact: '',
      guardianEmail: '',
      consentGiven: false,
      notes: '',
      submitting: false,
      errorMessage: '',
      resultMessage: '',
      paymentLink: '',
    };
  },
  computed: {
    // Mirrors Player Registration.set_age_and_minor_flag() client-side,
    // purely to decide whether to show the guardian fields - the server
    // is still the one that actually enforces this (validate_guardian_
    // consent()) once the booking is submitted.
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
    sessionFee() {
      if (!this.selectedSlot || !this.selectedPlayer.hourly_rate) return 0;
      return Number(this.selectedPlayer.hourly_rate) * this.slotHours(this.selectedSlot);
    },
    canSubmit() {
      if (!this.selectedSlot || !this.participantName || !this.dateOfBirth) return false;
      if (this.isMinor && !(this.guardianName && this.guardianContact && this.consentGiven)) return false;
      if (this.isGuest) {
        if (!this.email) return false;
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
    shortTime(value) {
      const parts = String(value).split(':');
      let h = parseInt(parts[0], 10);
      const m = parts[1];
      const ampm = h >= 12 ? 'PM' : 'AM';
      h = h % 12 || 12;
      return h + ':' + m + ' ' + ampm;
    },
    slotHours(slot) {
      const [sh, sm] = slot.start_time.split(':').map(Number);
      const [eh, em] = slot.end_time.split(':').map(Number);
      return (eh * 60 + em - (sh * 60 + sm)) / 60;
    },
    pickPlayer(p) {
      this.selectedPlayer = p;
      this.step = 'detail';
      this.selectedDate = this.today;
      this.selectedSlot = null;
      this.participantName = '';
      this.dateOfBirth = '';
      this.otp = '';
      this.otpSent = false;
      this.errorMessage = '';
      this.loadSlots();
    },
    backToGrid() {
      this.step = 'grid';
      this.selectedSlot = null;
    },
    loadSlots() {
      this.selectedSlot = null;
      if (!this.selectedDate) {
        this.slots = [];
        return;
      }
      this.loadingSlots = true;
      frappe.call(
        'sports_complex.sports_complex.doctype.player_session.player_session.get_player_available_slots',
        { player: this.selectedPlayer.name, date: this.selectedDate }
      ).then((r) => {
        this.slots = r.message || [];
      }).finally(() => {
        this.loadingSlots = false;
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
    submitBooking() {
      if (!this.canSubmit || this.submitting) return;
      this.submitting = true;
      this.errorMessage = '';

      const payload = {
        player: this.selectedPlayer.name,
        date: this.selectedDate,
        start_time: this.selectedSlot.start_time,
        end_time: this.selectedSlot.end_time,
        full_name: this.participantName,
        date_of_birth: this.dateOfBirth,
        notes: this.notes,
        guardian_name: this.guardianName,
        guardian_relationship: this.guardianRelationship,
        guardian_contact: this.guardianContact,
        guardian_email: this.guardianEmail,
        consent_given: this.consentGiven ? 1 : 0,
      };

      let method = 'sports_complex.sports_complex.doctype.player_session.player_session.create_player_booking';
      if (this.isGuest) {
        method = 'sports_complex.sports_complex.doctype.player_session.player_session.create_guest_player_booking';
        payload.email = this.email;
        payload.otp = this.otp;
        payload.remember_token = this.guestRememberToken;
      }

      frappe.call(method, payload).then((r) => {
        const msg = r.message || {};
        if (this.isGuest && msg.remember_token) {
          saveRemembered(this.email, msg.remember_token);
          this.guestRememberToken = msg.remember_token;
        }
        this.resultMessage = 'Your session with ' + this.selectedPlayer.full_name + ' on ' + this.selectedDate + ' is booked.';
        this.paymentLink = msg.payment_link || '';
        this.step = 'result';
      }).catch((err) => {
        if (!hasServerMessage(err)) {
          this.errorMessage = 'Could not book this session - please try again.';
        }
      }).finally(() => {
        this.submitting = false;
      });
    },
  },
}).mount('#app');
