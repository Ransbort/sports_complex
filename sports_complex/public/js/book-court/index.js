const { createApp } = Vue;

createApp({
  delimiters: ['[[', ']]'],
  data() {
    const now = new Date();
    const today = now.toISOString().slice(0, 10);
    return {
      facilities: window.facilities || [],
      isGuest: !!window.isGuest,
      step: 'grid', // 'grid' -> 'browse' -> 'details' -> 'result'
      today,
      selectedFacility: '',
      selectedDate: today,
      dowLabels: ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'],
      visibleYear: now.getFullYear(),
      visibleMonth: now.getMonth() + 1, // 1-12
      monthAvailability: {},
      loadingMonth: false,
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
    selectedFacilityInfo() {
      return this.facilities.find(f => f.name === this.selectedFacility) || {};
    },
    daysInMonth() {
      const count = new Date(this.visibleYear, this.visibleMonth, 0).getDate();
      return Array.from({ length: count }, (_, i) => i + 1);
    },
    leadingBlanks() {
      const count = new Date(this.visibleYear, this.visibleMonth - 1, 1).getDay();
      return Array.from({ length: count }, (_, i) => i);
    },
    monthLabel() {
      return new Date(this.visibleYear, this.visibleMonth - 1, 1)
        .toLocaleString(undefined, { month: 'long', year: 'numeric' });
    },
    isPrevMonthDisabled() {
      const now = new Date();
      return this.visibleYear === now.getFullYear() && this.visibleMonth === now.getMonth() + 1;
    },
  },
  methods: {
    fmt(amount) {
      return Number(amount || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    },
    pad2(n) {
      return String(n).padStart(2, '0');
    },
    dayKey(day) {
      return `${this.visibleYear}-${this.pad2(this.visibleMonth)}-${this.pad2(day)}`;
    },
    isToday(day) {
      return this.dayKey(day) === this.today;
    },
    isSelected(day) {
      return this.dayKey(day) === this.selectedDate;
    },
    isPastDay(day) {
      return this.dayKey(day) < this.today;
    },
    selectDay(day) {
      if (this.isPastDay(day)) return;
      this.selectedDate = this.dayKey(day);
      this.checkAvailability();
    },
    shiftMonth(delta) {
      let m = this.visibleMonth + delta;
      let y = this.visibleYear;
      if (m < 1) { m = 12; y -= 1; }
      if (m > 12) { m = 1; y += 1; }
      this.visibleMonth = m;
      this.visibleYear = y;
      this.loadMonthAvailability();
    },
    prevMonth() {
      if (this.isPrevMonthDisabled) return;
      this.shiftMonth(-1);
    },
    nextMonth() {
      this.shiftMonth(1);
    },
    loadMonthAvailability() {
      if (!this.selectedFacility) return;
      this.loadingMonth = true;
      // The loading flag is reset in both the success and error branches
      // below (rather than in a trailing .finally()) so the calendar can't
      // get stuck showing "Loading availability..." if the frappe.call
      // promise this site's version returns doesn't support .finally().
      frappe.call(
        'sports_complex.sports_complex.doctype.facility_booking.facility_booking.get_month_availability',
        { sports_facility: this.selectedFacility, year: this.visibleYear, month: this.visibleMonth }
      ).then(r => {
        this.monthAvailability = r.message || {};
        this.loadingMonth = false;
      }).catch(() => {
        // Non-fatal: the calendar still works for picking a day and
        // checking that day's slots directly - just without the dots.
        this.loadingMonth = false;
      });
    },
    pickFacility(facility) {
      this.selectedFacility = facility.name;
      this.step = 'browse';
      const now = new Date();
      this.visibleYear = now.getFullYear();
      this.visibleMonth = now.getMonth() + 1;
      this.monthAvailability = {};
      this.loadMonthAvailability();
      this.checkAvailability();
    },
    checkAvailability() {
      this.loadingSlots = true;
      this.slotsChecked = false;
      frappe.call(
        'sports_complex.sports_complex.doctype.facility_booking.facility_booking.get_available_slots',
        { sports_facility: this.selectedFacility, date: this.selectedDate }
      ).then(r => {
        this.slots = r.message || [];
        this.slotsChecked = true;
        this.loadingSlots = false;
      }).catch(() => {
        Swal.fire('Error', 'Could not load availability. Please try again.', 'error');
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
          sports_facility: this.selectedFacility,
          booking_date: this.selectedDate,
          start_time: this.selectedSlot.start_time,
          end_time: this.selectedSlot.end_time,
        }
      ).then(r => {
        this.result = r.message;
        this.step = 'result';
        this.booking = false;
      }).catch(() => {
        Swal.fire('Error', 'Could not create the booking. It may have just been taken - please choose another slot.', 'error');
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
        this.sendingOtp = false;
      }).catch(() => {
        Swal.fire('Error', 'Could not send the verification code. Please check the email address and try again.', 'error');
        this.sendingOtp = false;
      });
    },
    confirmGuestBooking() {
      this.booking = true;
      frappe.call(
        'sports_complex.sports_complex.doctype.facility_booking.facility_booking.create_guest_booking',
        {
          sports_facility: this.selectedFacility,
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
        this.booking = false;
      }).catch(() => {
        Swal.fire('Error', 'Could not verify the code or create the booking. Please try again.', 'error');
        this.booking = false;
      });
    },
  },
}).mount('#app');
