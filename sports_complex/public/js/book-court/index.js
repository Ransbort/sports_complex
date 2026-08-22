const { createApp } = Vue;

createApp({
  delimiters: ['[[', ']]'],
  data() {
    const today = new Date().toISOString().slice(0, 10);
    return {
      courts: window.courts || [],
      isGuest: !!window.isGuest,
      step: 'browse', // 'browse' -> 'details' -> 'result'
      today,
      selectedCourt: '',
      selectedDate: today,
      loadingSlots: false,
      slotsChecked: false,
      slots: [],
      selectedSlot: null,
      guestName: '',
      guestEmail: '',
      guestPhone: '',
      guestOtp: '',
      otpSent: false,
      sendingOtp: false,
      booking: false,
      result: null,
    };
  },
  computed: {
    canSendOtp() {
      return this.guestName.trim() && /\S+@\S+\.\S+/.test(this.guestEmail);
    },
    confirmationUrl() {
      if (!this.result) return '#';
      const token = this.result.token ? `?token=${encodeURIComponent(this.result.token)}` : '';
      return `/booking-confirmation/${this.result.booking}${token}`;
    },
  },
  methods: {
    checkAvailability() {
      this.loadingSlots = true;
      this.slotsChecked = false;
      frappe.call(
        'sports_complex.sports_complex.doctype.facility_booking.facility_booking.get_available_slots',
        { court: this.selectedCourt, date: this.selectedDate }
      ).then(r => {
        this.slots = r.message || [];
        this.slotsChecked = true;
      }).catch(() => {
        Swal.fire('Error', 'Could not load availability. Please try again.', 'error');
      }).finally(() => {
        this.loadingSlots = false;
      });
    },
    selectSlot(slot) {
      this.selectedSlot = slot;
      this.step = 'details';
    },
    confirmBooking() {
      this.booking = true;
      frappe.call(
        'sports_complex.sports_complex.doctype.facility_booking.facility_booking.create_booking',
        {
          court: this.selectedCourt,
          booking_date: this.selectedDate,
          start_time: this.selectedSlot.start_time,
          end_time: this.selectedSlot.end_time,
        }
      ).then(r => {
        this.result = r.message;
        this.step = 'result';
      }).catch(() => {
        Swal.fire('Error', 'Could not create the booking. It may have just been taken - please choose another slot.', 'error');
      }).finally(() => {
        this.booking = false;
      });
    },
    sendOtp() {
      this.sendingOtp = true;
      frappe.call(
        'sports_complex.utils.guest_booking.send_booking_otp',
        { email: this.guestEmail }
      ).then(() => {
        this.otpSent = true;
      }).catch(() => {
        Swal.fire('Error', 'Could not send the verification code. Please check the email address and try again.', 'error');
      }).finally(() => {
        this.sendingOtp = false;
      });
    },
    confirmGuestBooking() {
      this.booking = true;
      frappe.call(
        'sports_complex.sports_complex.doctype.facility_booking.facility_booking.create_guest_booking',
        {
          court: this.selectedCourt,
          booking_date: this.selectedDate,
          start_time: this.selectedSlot.start_time,
          end_time: this.selectedSlot.end_time,
          email: this.guestEmail,
          otp: this.guestOtp,
          full_name: this.guestName,
          phone: this.guestPhone,
        }
      ).then(r => {
        this.result = r.message;
        this.step = 'result';
      }).catch(() => {
        Swal.fire('Error', 'Could not verify the code or create the booking. Please try again.', 'error');
      }).finally(() => {
        this.booking = false;
      });
    },
  },
}).mount('#app');
