// Copyright (c) 2026, Your Company and contributors
// For license information, please see license.txt

// Front-desk check-in/check-out board for Facility Booking. Visually ported
// from healthcare's rehab_portal.js (see apps/healthcare/healthcare/
// healthcare/page/rehab_portal/) - same toolbar/icon-badge/stat-tiles/
// search-card/card-grid/status-badge/empty-state language, re-namespaced
// under "fci-" instead of "rehab-" so nothing collides if both pages are
// ever open at once. Structurally this page still differs from rehab_portal
// where the domain calls for it: two live queues side by side (Ready to
// Check In / Currently Checked In) rather than rehab's click-through tabs,
// since front-desk staff need to see both at a glance rather than switch
// between them. Every check-in/check-out mutation still just creates/
// submits a real Check-In or Check-Out document - see check_in.py/
// check_out.py for the actual state-machine logic (status transitions,
// overage billing); this page never re-implements it. The "Book
// Facility" button is the one exception - it's a front door onto
// Facility Booking itself (staff-facing counterpart to the public
// /book-facility flow), not the check-in/check-out queues below it; see
// create_staff_booking() in facility_booking.py for the actual booking
// creation/validation.

frappe.pages["facility-checkin"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Facility Check-In"),
		single_column: true,
	});

	new FacilityCheckinBoard(page);
};

class FacilityCheckinBoard {
	constructor(page) {
		this.page = page;
		this.filters = {
			facility: null,
			// Empty, not today - a fresh load (or a plain browser refresh)
			// should show every ready/checked-in booking by default, not just
			// today's. Staff can still narrow to a specific day with the
			// Date field below.
			date: null,
			customer: "",
			facility_booking: null,
		};
		this.readyBookings = [];
		this.checkedInBookings = [];
		this.currentView = "card";

		this.render_shell();
		this.setup_filters();
		this.setup_customer_search();
		this.refresh_all();
	}

	render_shell() {
		const style = `
			<style>
				/* Bound to the viewport - like pharmacy_pos's POS layout - instead
				   of growing with content and letting the whole desk page
				   scroll. That's what let the panels below spill past the
				   bottom of the screen: .fci-scrollable-content used a
				   max-height guessed from a fixed pixel offset, which didn't
				   actually match the real (variable) height of everything
				   above it, so cards overflowed the panel instead of scrolling
				   inside it. Fixing the wrapper to the viewport and using
				   flex: 1 / min-height: 0 down the chain (see fci-columns,
				   fci-column-panel, fci-scrollable-content below) makes each
				   scroll region exactly as tall as the space actually left
				   over, however tall the header ends up rendering. */
				.fci-wrapper {
					height: calc(100vh - 60px);
					box-sizing: border-box;
					display: flex;
					flex-direction: column;
					padding: 20px;
					max-width: 1400px;
					margin: 0 auto;
					overflow: hidden;
				}

				.fci-top-section {
					flex-shrink: 0;
				}

				.fci-toolbar {
					display: flex;
					justify-content: space-between;
					align-items: center;
					padding-bottom: 16px;
					margin-bottom: 16px;
					border-bottom: 1px solid #e9ecef;
				}

				.fci-toolbar-title {
					display: flex;
					align-items: center;
					gap: 12px;
				}

				.fci-toolbar-title .fci-icon-badge {
					width: 40px;
					height: 40px;
					border-radius: 10px;
					background: #f0f1fe;
					color: var(--primary-color);
					display: flex;
					align-items: center;
					justify-content: center;
					font-size: 17px;
					flex-shrink: 0;
				}

				.fci-toolbar-title h4 {
					margin: 0;
					font-size: 1.2rem;
					font-weight: 700;
					color: #1a1a2e;
					line-height: 1.3;
				}

				.fci-toolbar-title .fci-toolbar-subtitle {
					font-size: 0.83rem;
					color: #868e96;
					margin-top: 1px;
				}

				.fci-toolbar-actions {
					display: flex;
					align-items: center;
					gap: 10px;
				}

				.fci-btn-icon {
					width: 38px;
					height: 38px;
					border-radius: 8px;
					border: 1px solid #dee2e6;
					background: white;
					color: #495057;
					display: flex;
					align-items: center;
					justify-content: center;
					cursor: pointer;
					transition: all 0.15s ease;
					font-size: 0.95rem;
				}

				.fci-btn-icon:hover {
					background: #f8f9fa;
					border-color: var(--primary-color);
					color: var(--primary-color);
				}

				.fci-btn-book {
					display: flex;
					align-items: center;
					gap: 7px;
					height: 38px;
					padding: 0 16px;
					border-radius: 8px;
					font-weight: 600;
					font-size: 0.88rem;
					border: none;
					background: var(--primary-color);
					color: white;
					cursor: pointer;
					transition: all 0.15s ease;
				}

				.fci-btn-book:hover {
					opacity: 0.9;
				}

				.fci-slot-picker-header {
					display: flex;
					justify-content: space-between;
					align-items: center;
					font-size: 0.83rem;
					color: #6c757d;
					margin-bottom: 8px;
				}

				.fci-slot-select-all {
					cursor: pointer;
					font-weight: 600;
				}

				.fci-slot-picker-grid {
					display: grid;
					grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
					gap: 8px;
					max-height: 220px;
					overflow-y: auto;
					padding-right: 4px;
				}

				.fci-slot-chip {
					border: 1px solid #dee2e6;
					border-radius: 8px;
					padding: 8px 10px;
					font-size: 0.83rem;
					font-weight: 600;
					text-align: center;
					cursor: pointer;
					transition: all 0.15s ease;
					user-select: none;
				}

				.fci-slot-chip:hover {
					border-color: var(--primary-color);
					color: var(--primary-color);
				}

				.fci-slot-chip.selected {
					background: var(--primary-color);
					border-color: var(--primary-color);
					color: white;
				}

				.fci-btn-outline {
					display: flex;
					align-items: center;
					gap: 7px;
					height: 38px;
					padding: 0 14px;
					border-radius: 8px;
					font-weight: 600;
					font-size: 0.88rem;
					border: 1px solid #dee2e6;
					background: white;
					color: #495057;
					cursor: pointer;
					transition: all 0.15s ease;
				}

				.fci-btn-outline:hover {
					border-color: var(--primary-color);
					color: var(--primary-color);
				}

				.fci-all-bookings-table {
					width: 100%;
					border-collapse: collapse;
					font-size: 0.85rem;
				}

				.fci-all-bookings-table thead {
					background: #f8f9fa;
				}

				.fci-all-bookings-table th {
					padding: 8px 10px;
					text-align: left;
					font-weight: 600;
					font-size: 0.78rem;
					color: #6c757d;
					text-transform: uppercase;
					border-bottom: 1px solid #e9ecef;
				}

				.fci-all-bookings-table td {
					padding: 8px 10px;
					vertical-align: middle;
					border-bottom: 1px solid #f1f3f5;
				}

				.fci-status-payment-pending { background: #ffe8cc; color: #9c5500; }
				.fci-status-draft { background: #e9ecef; color: #495057; }
				.fci-status-completed { background: #d3f9d8; color: #2b8a3e; }
				.fci-status-cancelled { background: #f1f3f5; color: #868e96; }
				.fci-status-noshow { background: #f8d7da; color: #721c24; }

				.fci-view-toggle-group {
					display: flex;
					gap: 5px;
					border: 1px solid #e0e0e0;
					border-radius: 6px;
					padding: 2px;
					background: #f8f9fa;
				}

				.fci-view-toggle-btn {
					width: 32px;
					height: 32px;
					display: flex;
					align-items: center;
					justify-content: center;
					background: transparent;
					border: none;
					color: #6c757d;
					cursor: pointer;
					border-radius: 4px;
					transition: all 0.2s ease;
				}

				.fci-view-toggle-btn:hover {
					background: rgba(102, 126, 234, 0.1);
					color: var(--primary-color);
				}

				.fci-view-toggle-btn.active {
					background: white;
					color: var(--primary-color);
					box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
				}

				.fci-wrapper .fci-search-section {
					background: #ffffff !important;
					background-image: none !important;
					border: 1px solid #e9ecef;
					border-radius: 12px;
					padding: 20px 20px 14px;
					margin-bottom: 4px;
					box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
				}

				.fci-search-input-group {
					display: grid;
					grid-template-columns: 1fr 1fr 1fr 1fr auto;
					gap: 14px;
					align-items: end;
				}

				.fci-search-input-group .frappe-control { flex: 1; }
				.fci-search-input-group .form-group { margin-bottom: 0; }
				.fci-wrapper .fci-search-input-group label {
					color: #495057 !important;
					font-weight: 500;
					font-size: 0.83rem;
				}

				.fci-search-input-group .form-control {
					border-radius: 8px;
					border: 1px solid #dee2e6;
				}

				#fci-clear-btn {
					border-radius: 8px;
					font-weight: 600;
					padding: 8px 16px;
					background: transparent;
					border: 1px solid #dee2e6;
					color: #495057;
				}

				#fci-clear-btn:hover { background: #f8f9fa; }

				.fci-wrapper .fci-last-updated {
					display: flex;
					align-items: center;
					gap: 6px;
					font-size: 0.78rem;
					color: #adb5bd !important;
					padding: 10px 2px 2px;
				}

				.fci-stats-bar {
					display: grid;
					grid-template-columns: repeat(4, 1fr);
					gap: 12px;
					margin: 16px 0;
				}

				.fci-stat-tile {
					background: white;
					border: 1px solid #e9ecef;
					border-radius: 10px;
					padding: 14px 16px;
					box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
				}

				.fci-stat-tile .fci-stat-label {
					font-size: 0.78rem;
					color: #868e96;
					font-weight: 500;
					margin-bottom: 4px;
				}

				.fci-stat-tile .fci-stat-value {
					font-size: 1.35rem;
					font-weight: 700;
					color: #2c3e50;
				}

				.fci-stat-tile.stat-orange .fci-stat-value { color: #fd7e14; }
				.fci-stat-tile.stat-green .fci-stat-value { color: #28a745; }
				.fci-stat-tile.stat-blue .fci-stat-value { color: #667eea; }
				.fci-stat-tile.stat-red .fci-stat-value { color: #dc3545; }

				.fci-columns {
					flex: 1;
					min-height: 0;
					display: grid;
					grid-template-columns: 1fr 1fr;
					gap: 20px;
					overflow: hidden;
				}

				.fci-column-panel {
					background: white;
					border: 1px solid #e9ecef;
					border-radius: 12px;
					box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
					padding: 16px;
					display: flex;
					flex-direction: column;
					min-height: 0;
					overflow: hidden;
				}

				.fci-column-header {
					flex-shrink: 0;
					display: flex;
					align-items: center;
					gap: 8px;
					padding-bottom: 12px;
					margin-bottom: 14px;
					border-bottom: 2px solid var(--primary-color);
					font-weight: 600;
					font-size: 1rem;
					color: #2c3e50;
				}

				.fci-column-header .badge {
					margin-left: auto;
					font-size: 0.8rem;
					padding: 3px 8px;
				}

				.fci-scrollable-content {
					flex: 1;
					min-height: 0;
					overflow-y: auto;
					overflow-x: hidden;
					padding-right: 6px;
				}

				.fci-scrollable-content::-webkit-scrollbar { width: 8px; }
				.fci-scrollable-content::-webkit-scrollbar-track { background: #f1f1f1; border-radius: 4px; }
				.fci-scrollable-content::-webkit-scrollbar-thumb { background: #ccc; border-radius: 4px; }
				.fci-scrollable-content::-webkit-scrollbar-thumb:hover { background: #aaa; }

				.fci-cards-container {
					display: grid;
					grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
					gap: 14px;
				}

				.fci-list-table {
					width: 100%;
					border-collapse: collapse;
					font-size: 0.85rem;
				}

				.fci-list-table thead {
					background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
					color: white;
				}

				.fci-list-table th {
					padding: 10px 12px;
					text-align: left;
					font-weight: 600;
					font-size: 0.82rem;
				}

				.fci-list-table tbody tr {
					border-bottom: 1px solid #e9ecef;
					transition: background 0.2s ease;
				}

				.fci-list-table tbody tr:hover { background: #f8f9fa; }

				.fci-list-table td {
					padding: 10px 12px;
					vertical-align: middle;
				}

				.fci-list-table .fci-btn-action { padding: 5px 12px; font-size: 0.8rem; }

				.fci-card {
					background: white;
					border: 2px solid #e0e0e0;
					border-radius: 12px;
					padding: 16px;
					cursor: default;
					transition: all 0.3s ease;
					box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
				}

				.fci-card:hover {
					border-color: var(--primary-color);
					box-shadow: 0 4px 16px rgba(102, 126, 234, 0.2);
					transform: translateY(-2px);
				}

				.fci-card-header {
					display: flex;
					justify-content: space-between;
					align-items: start;
					margin-bottom: 12px;
					padding-bottom: 12px;
					border-bottom: 1px solid #e9ecef;
				}

				.fci-card-title {
					font-size: 1.05rem;
					font-weight: 700;
					color: #2c3e50;
					margin-bottom: 3px;
					overflow: hidden;
					text-overflow: ellipsis;
					white-space: nowrap;
					max-width: 170px;
				}

				.fci-card-subtitle { font-size: 0.85rem; color: #6c757d; }

				.fci-pill-badge {
					padding: 4px 10px;
					border-radius: 12px;
					font-size: 0.72rem;
					font-weight: 600;
					text-transform: uppercase;
					white-space: nowrap;
				}

				.fci-pill-unpaid { background: #f8d7da; color: #721c24; }
				.fci-pill-late { background: #f8d7da; color: #721c24; }

				.fci-card-body { margin-bottom: 12px; }
				.fci-card-info { display: flex; flex-direction: column; gap: 7px; }

				.fci-info-row { display: flex; align-items: center; font-size: 0.87rem; }
				.fci-info-row i { width: 18px; color: #6c757d; margin-right: 8px; }
				.fci-info-label { color: #6c757d; margin-right: 5px; }
				.fci-info-value { color: #2c3e50; font-weight: 600; }

				.fci-info-row.fci-info-late { background: #fdecea; padding: 6px 8px; border-radius: 6px; margin-top: 2px; }
				.fci-info-row.fci-info-late .fci-info-value { color: #c0392b; }

				.fci-card-footer {
					display: flex;
					justify-content: space-between;
					align-items: center;
					padding-top: 12px;
					border-top: 1px solid #e9ecef;
				}

				.fci-status-badge { padding: 5px 11px; border-radius: 8px; font-size: 0.8rem; font-weight: 600; }
				.fci-status-confirmed { background: #cfe2ff; color: #084298; }
				.fci-status-checkedin { background: #fff3cd; color: #856404; }

				.fci-btn-action { padding: 7px 14px; font-size: 0.85rem; font-weight: 600; border-radius: 8px; }

				.fci-empty-state {
					grid-column: 1 / -1;
					text-align: center;
					padding: 40px 20px;
					color: #6c757d;
				}

				.fci-empty-state i { font-size: 42px; margin-bottom: 14px; opacity: 0.3; }
				.fci-empty-state p { font-size: 0.92rem; margin: 0; }

				@media (max-width: 900px) {
					/* Two panels side by side no longer fit - stack them and
					   let this row scroll as a whole instead of trying to
					   keep two independently-scrolling panels alive in too
					   little width. */
					.fci-columns {
						grid-template-columns: 1fr;
						overflow-y: auto;
						overflow-x: hidden;
					}
					.fci-column-panel { max-height: 50vh; }
					.fci-stats-bar { grid-template-columns: 1fr 1fr; }
				}

				@media (max-width: 768px) {
					.fci-wrapper { padding: 15px; }
					.fci-toolbar { flex-direction: column; align-items: flex-start; gap: 12px; }
					.fci-toolbar-actions { width: 100%; justify-content: flex-end; }
					.fci-search-input-group { grid-template-columns: 1fr; }
				}
			</style>
		`;
		$(style).appendTo(this.page.main);

		const html = `
			<div class="fci-wrapper">
				<div class="fci-top-section">
					<div class="fci-toolbar">
						<div class="fci-toolbar-title">
							<div class="fci-icon-badge"><i class="fa fa-door-open"></i></div>
							<div>
								<h4>${__("Facility Check-In")}</h4>
								<div class="fci-toolbar-subtitle">${__("Search bookings and check customers in or out")}</div>
							</div>
						</div>
						<div class="fci-toolbar-actions">
							<button class="fci-btn-outline" id="fci-cashier-btn">
								<i class="fa fa-money"></i> ${__("Cashier")}
							</button>
							<button class="fci-btn-outline" id="fci-all-bookings-btn">
								<i class="fa fa-list-alt"></i> ${__("All Bookings")}
							</button>
							<button class="fci-btn-book" id="fci-book-btn">
								<i class="fa fa-plus"></i> ${__("Book Facility")}
							</button>
							<div class="fci-view-toggle-group">
								<button class="fci-view-toggle-btn active" data-view="card" title="${__("Card View")}">
									<i class="fa fa-th-large"></i>
								</button>
								<button class="fci-view-toggle-btn" data-view="list" title="${__("List View")}">
									<i class="fa fa-list"></i>
								</button>
							</div>
							<button class="fci-btn-icon" id="fci-refresh-btn" title="${__("Refresh")}">
								<i class="fa fa-refresh"></i>
							</button>
						</div>
					</div>

					<div class="fci-search-section">
						<div class="fci-search-input-group">
							<div class="frappe-control" data-fieldname="facility"></div>
							<div class="frappe-control" data-fieldname="date"></div>
							<div class="frappe-control" data-fieldname="customer"></div>
							<div class="frappe-control" data-fieldname="facility_booking"></div>
							<button class="btn" id="fci-clear-btn">${__("Clear Filters")}</button>
						</div>
						<div class="fci-last-updated">
							<i class="fa fa-clock-o"></i>
							<span id="fci-last-updated-time">${__("Not loaded yet")}</span>
						</div>
					</div>

					<div class="fci-stats-bar" id="fci-stats-bar"></div>
				</div>

				<div class="fci-columns">
					<div class="fci-column-panel">
						<div class="fci-column-header">
							<i class="fa fa-sign-in"></i> ${__("Ready to Check In")}
							<span class="badge badge-info" id="fci-ready-count">0</span>
						</div>
						<div class="fci-scrollable-content">
							<div class="fci-cards-container" data-column="ready"></div>
							<div class="fci-list-container" data-column="ready" style="display: none;"></div>
						</div>
					</div>
					<div class="fci-column-panel">
						<div class="fci-column-header">
							<i class="fa fa-sign-out"></i> ${__("Currently Checked In")}
							<span class="badge badge-warning" id="fci-checkedin-count">0</span>
						</div>
						<div class="fci-scrollable-content">
							<div class="fci-cards-container" data-column="checked-in"></div>
							<div class="fci-list-container" data-column="checked-in" style="display: none;"></div>
						</div>
					</div>
				</div>
			</div>
		`;
		$(html).appendTo(this.page.main);

		this.$ready_list = this.page.main.find('.fci-cards-container[data-column="ready"]');
		this.$checked_in_list = this.page.main.find('.fci-cards-container[data-column="checked-in"]');
		this.$ready_table = this.page.main.find('.fci-list-container[data-column="ready"]');
		this.$checked_in_table = this.page.main.find('.fci-list-container[data-column="checked-in"]');
		this.$ready_count = this.page.main.find("#fci-ready-count");
		this.$checked_in_count = this.page.main.find("#fci-checkedin-count");

		this.page.main.find("#fci-refresh-btn").on("click", () => this.refresh_all());
		this.page.main.find("#fci-book-btn").on("click", () => this.open_book_facility_dialog());
		this.page.main.find("#fci-all-bookings-btn").on("click", () => this.open_all_bookings_dialog());
		// Real payment collection (an actual Payment Entry) lives on the
		// dedicated Cashier page, not here - see that page's own module
		// docstring for why it's a separate page rather than a third thing
		// bolted onto this one. There used to be a "Mark Paid & Confirm"
		// attestation shortcut in the All Bookings panel below and a
		// "Payment Collected" checkbox on the Book Facility dialog that
		// both skipped straight to Facility Booking.mark_paid_and_confirm()
		// with no Payment Entry ever created - that left the booking
		// reading Paid while its Sales Invoice sat Unpaid. Both were
		// removed; the Cashier page is the one place that flow now exists.
		this.page.main.find("#fci-cashier-btn").on("click", () => frappe.set_route("cashier", "facility"));

		this.page.main.find(".fci-view-toggle-btn").on("click", (e) => {
			const view = $(e.currentTarget).attr("data-view");
			if (view === this.currentView) return;
			this.currentView = view;
			this.page.main.find(".fci-view-toggle-btn").removeClass("active");
			this.page.main.find(`.fci-view-toggle-btn[data-view="${view}"]`).addClass("active");
			this.render_ready_list();
			this.render_checked_in_list();
		});
	}

	setup_filters() {
		this.facility_control = frappe.ui.form.make_control({
			parent: this.page.main.find('.frappe-control[data-fieldname="facility"]'),
			df: {
				fieldtype: "Link",
				fieldname: "facility",
				options: "Sports Facility",
				label: __("Facility"),
				placeholder: __("Filter by facility"),
				get_query: () => ({ filters: { status: "Active" } }),
				onchange: () => {
					this.filters.facility = this.facility_control.get_value() || null;
					this.refresh_all();
				},
			},
			render_input: true,
		});
		this.facility_control.refresh();

		this.date_control = frappe.ui.form.make_control({
			parent: this.page.main.find('.frappe-control[data-fieldname="date"]'),
			df: {
				fieldtype: "Date",
				fieldname: "date",
				label: __("Date"),
				default: this.filters.date,
				onchange: () => {
					// Empty by default (shows every date) - staff can narrow to
					// one day here, and clearing the field must actually clear
					// the filter again rather than snapping back to a value.
					const val = this.date_control.get_value() || "";
					// get_value() already reflects the real (possibly now-
					// empty) value - proven by the query itself picking it up
					// correctly - so only the DISPLAYED text needs correcting
					// here. Calling set_value() to do that re-fires this same
					// onchange handler (Frappe re-triggers onchange on every
					// set_value() call, not just user-driven ones), which
					// then calls set_value() again, and again, forever - that
					// infinite loop is what was freezing the tab and eating
					// memory on every page load (setup_filters() below calls
					// set_value() once up front, which was enough to kick it
					// off immediately). Writing straight to the input element
					// fixes the same visual snap-back without going back
					// through set_value()'s onchange-triggering pipeline.
					this.date_control.$input.val(val ? frappe.datetime.str_to_user(val) : "");
					this.filters.date = val || null;
					this.refresh_all();
				},
			},
			render_input: true,
		});
		this.date_control.set_value(this.filters.date);
		this.date_control.refresh();

		this.facility_booking_control = frappe.ui.form.make_control({
			parent: this.page.main.find('.frappe-control[data-fieldname="facility_booking"]'),
			df: {
				fieldtype: "Link",
				fieldname: "facility_booking",
				options: "Facility Booking",
				label: __("Facility Booking"),
				placeholder: __("Jump to a booking..."),
				// Only bookings this board can actually act on - matches the
				// same statuses get_ready_to_check_in()/get_checked_in() list,
				// so staff can't pick a Completed/Cancelled booking that would
				// just come back empty.
				get_query: () => ({ filters: { booking_status: ["in", ["Confirmed", "Checked-In"]] } }),
				onchange: () => {
					this.filters.facility_booking = this.facility_booking_control.get_value() || null;
					this.refresh_all();
				},
			},
			render_input: true,
		});
		this.facility_booking_control.refresh();

		this.page.main.find("#fci-clear-btn").on("click", () => {
			// "Clear Filters" means show everything - including every date,
			// not just today, so this blanks the Date field rather than
			// resetting it back to today.
			this.facility_control.set_value("");
			this.customer_control.set_value("");
			this.facility_booking_control.set_value("");
			this.date_control.set_value("");
			this.filters = { facility: null, date: null, customer: "", facility_booking: null };
			this.refresh_all();
		});
	}

	setup_customer_search() {
		this.customer_control = frappe.ui.form.make_control({
			parent: this.page.main.find('.frappe-control[data-fieldname="customer"]'),
			df: {
				fieldtype: "Data",
				fieldname: "customer",
				label: __("Search Customer"),
				placeholder: __("Customer name..."),
			},
			render_input: true,
		});
		this.customer_control.refresh();

		this.customer_control.$input.on(
			"input",
			frappe.utils.debounce(() => {
				this.filters.customer = this.customer_control.get_value() || "";
				this.refresh_all();
			}, 400)
		);
	}

	mark_load_done() {
		this._pending_loads = Math.max(0, (this._pending_loads || 1) - 1);
		if (this._pending_loads === 0) {
			const now = new Date();
			const timeStr = now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
			this.page.main.find("#fci-last-updated-time").text(__("Updated at {0}", [timeStr]));
		}
	}

	refresh_all() {
		this._pending_loads = 2;
		this.load_ready_to_check_in();
		this.load_checked_in();
	}

	get_common_args() {
		return {
			facility: this.filters.facility || null,
			date: this.filters.date || null,
			customer: this.filters.customer || null,
			facility_booking: this.filters.facility_booking || null,
		};
	}

	load_ready_to_check_in() {
		frappe.call({
			method: "sports_complex.sports_complex.page.facility_checkin.facility_checkin.get_ready_to_check_in",
			args: this.get_common_args(),
			callback: (r) => {
				this.readyBookings = r.message || [];
				this.render_ready_list();
				this.render_stats();
				this.mark_load_done();
			},
		});
	}

	load_checked_in() {
		frappe.call({
			method: "sports_complex.sports_complex.page.facility_checkin.facility_checkin.get_checked_in",
			args: this.get_common_args(),
			callback: (r) => {
				this.checkedInBookings = r.message || [];
				this.render_checked_in_list();
				this.render_stats();
				this.mark_load_done();
			},
		});
	}

	render_stats() {
		const unpaid = this.readyBookings.filter((b) => b.payment_status && b.payment_status !== "Paid").length;
		const now = moment();
		const running_late = this.checkedInBookings.filter((b) => {
			const scheduled_end = moment(`${b.booking_date} ${b.end_time}`);
			return scheduled_end.isValid() && now.isAfter(scheduled_end);
		}).length;

		this.page.main.find("#fci-stats-bar").html(`
			<div class="fci-stat-tile stat-blue">
				<div class="fci-stat-label">${__("Ready to Check In")}</div>
				<div class="fci-stat-value">${this.readyBookings.length}</div>
			</div>
			<div class="fci-stat-tile stat-orange">
				<div class="fci-stat-label">${__("Unpaid (Ready)")}</div>
				<div class="fci-stat-value">${unpaid}</div>
			</div>
			<div class="fci-stat-tile stat-green">
				<div class="fci-stat-label">${__("Currently Checked In")}</div>
				<div class="fci-stat-value">${this.checkedInBookings.length}</div>
			</div>
			<div class="fci-stat-tile stat-red">
				<div class="fci-stat-label">${__("Running Over")}</div>
				<div class="fci-stat-value">${running_late}</div>
			</div>
		`);
	}

	render_ready_list() {
		const bookings = this.readyBookings;
		this.$ready_count.text(bookings.length);

		if (!bookings.length) {
			const empty = `
				<div class="fci-empty-state">
					<i class="fa fa-coffee"></i>
					<p>${__("No bookings ready for check-in")}</p>
				</div>
			`;
			this.$ready_list.html(empty);
			this.$ready_table.html(empty);
		} else if (this.currentView === "card") {
			this.render_ready_cards(bookings);
		} else {
			this.render_ready_table(bookings);
		}

		this.$ready_list.toggle(this.currentView === "card");
		this.$ready_table.toggle(this.currentView === "list");
	}

	render_ready_cards(bookings) {
		this.$ready_list.html(
			bookings
				.map((b) => {
					const unpaid_badge =
						b.payment_status && b.payment_status !== "Paid"
							? `<span class="fci-pill-badge fci-pill-unpaid">${frappe.utils.escape_html(b.payment_status)}</span>`
							: "";
					return `
						<div class="fci-card" data-booking="${b.name}">
							<div class="fci-card-header">
								<div>
									<div class="fci-card-title">${frappe.utils.escape_html(b.customer || "")}</div>
									<div class="fci-card-subtitle">${frappe.utils.escape_html(b.facility_name || "")}</div>
								</div>
								${unpaid_badge}
							</div>
							<div class="fci-card-body">
								<div class="fci-card-info">
									<div class="fci-info-row">
										<i class="fa fa-calendar"></i>
										<span class="fci-info-label">${__("Date")}:</span>
										<span class="fci-info-value">${frappe.datetime.str_to_user(b.booking_date)}</span>
									</div>
									<div class="fci-info-row">
										<i class="fa fa-clock-o"></i>
										<span class="fci-info-label">${__("Time")}:</span>
										<span class="fci-info-value">${sc_fci_short_time(b.start_time)} - ${sc_fci_short_time(b.end_time)}</span>
									</div>
									<div class="fci-info-row">
										<i class="fa fa-money"></i>
										<span class="fci-info-label">${__("Amount")}:</span>
										<span class="fci-info-value">${format_currency(b.total_amount)}</span>
									</div>
								</div>
							</div>
							<div class="fci-card-footer">
								<span class="fci-status-badge fci-status-confirmed">${__("Confirmed")}</span>
								<div>
									<button class="btn btn-success fci-btn-action fci-checkin-btn" data-booking="${b.name}">
										<i class="fa fa-sign-in"></i> ${__("Check In")}
									</button>
								</div>
							</div>
						</div>
					`;
				})
				.join("")
		);

		this.$ready_list.find(".fci-checkin-btn").on("click", (e) => {
			const booking = $(e.currentTarget).attr("data-booking");
			this.open_check_in_dialog(booking);
		});
	}

	render_ready_table(bookings) {
		const rows = bookings
			.map((b) => {
				const payment = frappe.utils.escape_html(b.payment_status || "-");
				return `
					<tr>
						<td><strong>${frappe.utils.escape_html(b.customer || "")}</strong></td>
						<td>${frappe.utils.escape_html(b.facility_name || "")}</td>
						<td>${frappe.datetime.str_to_user(b.booking_date)}</td>
						<td>${sc_fci_short_time(b.start_time)} - ${sc_fci_short_time(b.end_time)}</td>
						<td>${format_currency(b.total_amount)}</td>
						<td>${payment}</td>
						<td>
							<button class="btn btn-success btn-sm fci-btn-action fci-checkin-btn" data-booking="${b.name}">
								<i class="fa fa-sign-in"></i> ${__("Check In")}
							</button>
						</td>
					</tr>
				`;
			})
			.join("");

		this.$ready_table.html(`
			<table class="fci-list-table">
				<thead>
					<tr>
						<th>${__("Customer")}</th>
						<th>${__("Facility")}</th>
						<th>${__("Date")}</th>
						<th>${__("Time")}</th>
						<th>${__("Amount")}</th>
						<th>${__("Payment")}</th>
						<th>${__("Action")}</th>
					</tr>
				</thead>
				<tbody>${rows}</tbody>
			</table>
		`);

		this.$ready_table.find(".fci-checkin-btn").on("click", (e) => {
			const booking = $(e.currentTarget).attr("data-booking");
			this.open_check_in_dialog(booking);
		});
	}

	render_checked_in_list() {
		const bookings = this.checkedInBookings;
		this.$checked_in_count.text(bookings.length);

		if (!bookings.length) {
			const empty = `
				<div class="fci-empty-state">
					<i class="fa fa-check-circle"></i>
					<p>${__("No one currently checked in")}</p>
				</div>
			`;
			this.$checked_in_list.html(empty);
			this.$checked_in_table.html(empty);
		} else if (this.currentView === "card") {
			this.render_checked_in_cards(bookings);
		} else {
			this.render_checked_in_table(bookings);
		}

		this.$checked_in_list.toggle(this.currentView === "card");
		this.$checked_in_table.toggle(this.currentView === "list");
	}

	render_checked_in_cards(bookings) {
		const now = moment();

		this.$checked_in_list.html(
			bookings
				.map((b) => {
					const scheduled_end = moment(`${b.booking_date} ${b.end_time}`);
					const is_late = scheduled_end.isValid() && now.isAfter(scheduled_end);
					const late_badge = is_late
						? `<span class="fci-pill-badge fci-pill-late">${__("Running late")}</span>`
						: "";

					return `
						<div class="fci-card" data-booking="${b.name}">
							<div class="fci-card-header">
								<div>
									<div class="fci-card-title">${frappe.utils.escape_html(b.customer || "")}</div>
									<div class="fci-card-subtitle">${frappe.utils.escape_html(b.facility_name || "")}</div>
								</div>
								${late_badge}
							</div>
							<div class="fci-card-body">
								<div class="fci-card-info">
									<div class="fci-info-row">
										<i class="fa fa-clock-o"></i>
										<span class="fci-info-label">${__("Scheduled end")}:</span>
										<span class="fci-info-value">${sc_fci_short_time(b.end_time)}</span>
									</div>
									${
										b.check_in_time
											? `<div class="fci-info-row">
													<i class="fa fa-sign-in"></i>
													<span class="fci-info-label">${__("In since")}:</span>
													<span class="fci-info-value">${sc_fci_short_datetime(b.check_in_time)}</span>
												</div>`
											: ""
									}
									${
										is_late
											? `<div class="fci-info-row fci-info-late">
													<i class="fa fa-exclamation-triangle"></i>
													<span class="fci-info-label">${__("Past scheduled end time")}</span>
												</div>`
											: ""
									}
								</div>
							</div>
							<div class="fci-card-footer">
								<span class="fci-status-badge fci-status-checkedin">${__("Checked-In")}</span>
								<div>
									<button class="btn btn-primary fci-btn-action fci-checkout-btn" data-booking="${b.name}">
										<i class="fa fa-sign-out"></i> ${__("Check Out")}
									</button>
								</div>
							</div>
						</div>
					`;
				})
				.join("")
		);

		this.$checked_in_list.find(".fci-checkout-btn").on("click", (e) => {
			const booking = $(e.currentTarget).attr("data-booking");
			this.open_check_out_dialog(booking);
		});
	}

	render_checked_in_table(bookings) {
		const now = moment();

		const rows = bookings
			.map((b) => {
				const scheduled_end = moment(`${b.booking_date} ${b.end_time}`);
				const is_late = scheduled_end.isValid() && now.isAfter(scheduled_end);
				const status = is_late
					? `<span class="fci-pill-badge fci-pill-late">${__("Running late")}</span>`
					: `<span class="fci-status-badge fci-status-checkedin">${__("Checked-In")}</span>`;

				return `
					<tr>
						<td><strong>${frappe.utils.escape_html(b.customer || "")}</strong></td>
						<td>${frappe.utils.escape_html(b.facility_name || "")}</td>
						<td>${sc_fci_short_time(b.end_time)}</td>
						<td>${b.check_in_time ? sc_fci_short_datetime(b.check_in_time) : "-"}</td>
						<td>${status}</td>
						<td>
							<button class="btn btn-primary btn-sm fci-btn-action fci-checkout-btn" data-booking="${b.name}">
								<i class="fa fa-sign-out"></i> ${__("Check Out")}
							</button>
						</td>
					</tr>
				`;
			})
			.join("");

		this.$checked_in_table.html(`
			<table class="fci-list-table">
				<thead>
					<tr>
						<th>${__("Customer")}</th>
						<th>${__("Facility")}</th>
						<th>${__("Scheduled End")}</th>
						<th>${__("In Since")}</th>
						<th>${__("Status")}</th>
						<th>${__("Action")}</th>
					</tr>
				</thead>
				<tbody>${rows}</tbody>
			</table>
		`);

		this.$checked_in_table.find(".fci-checkout-btn").on("click", (e) => {
			const booking = $(e.currentTarget).attr("data-booking");
			this.open_check_out_dialog(booking);
		});
	}

	open_check_in_dialog(facility_booking) {
		const booking = this.readyBookings.find((b) => b.name === facility_booking) || {};

		const dialog = new frappe.ui.Dialog({
			title: __("Check In {0}", [booking.customer || facility_booking]),
			fields: [
				{
					fieldtype: "HTML",
					fieldname: "summary",
					options: `
						<div class="fci-card-info">
							<div class="fci-info-row">
								<i class="fa fa-map-marker"></i>
								<span class="fci-info-label">${__("Facility")}:</span>
								<span class="fci-info-value">${frappe.utils.escape_html(booking.facility_name || "")}</span>
							</div>
							<div class="fci-info-row">
								<i class="fa fa-calendar"></i>
								<span class="fci-info-label">${__("Scheduled")}:</span>
								<span class="fci-info-value">
									${frappe.datetime.str_to_user(booking.booking_date)}
									${sc_fci_short_time(booking.start_time)} - ${sc_fci_short_time(booking.end_time)}
								</span>
							</div>
						</div>
					`,
				},
				{
					fieldtype: "Datetime",
					fieldname: "check_in_time",
					label: __("Check-In Time"),
					default: frappe.datetime.now_datetime(),
					reqd: 1,
				},
			],
			primary_action_label: __("Confirm Check-In"),
			primary_action: (values) => {
				dialog.hide();
				this.do_check_in(facility_booking, values.check_in_time);
			},
		});

		dialog.show();
	}

	do_check_in(facility_booking, check_in_time) {
		frappe.call({
			method: "sports_complex.sports_complex.page.facility_checkin.facility_checkin.check_in_booking",
			args: { facility_booking, check_in_time },
			freeze: true,
			freeze_message: __("Checking in..."),
			callback: (r) => {
				if (r.message && r.message.status === "Success") {
					frappe.show_alert({ message: __("Checked in"), indicator: "green" });
					this.refresh_all();
				}
			},
			error: (err) => {
				if (!(err && err._server_messages)) {
					frappe.show_alert({ message: __("Check-in failed"), indicator: "red" });
				}
			},
		});
	}

	open_check_out_dialog(facility_booking) {
		frappe.call({
			method: "sports_complex.sports_complex.page.facility_checkin.facility_checkin.get_checkout_preview",
			args: { facility_booking },
			freeze: true,
			freeze_message: __("Calculating..."),
			callback: (r) => {
				const preview = r.message;
				if (!preview) return;
				this.show_check_out_dialog(facility_booking, preview);
			},
			error: (err) => {
				if (!(err && err._server_messages)) {
					frappe.show_alert({ message: __("Could not load check-out details"), indicator: "red" });
				}
			},
		});
	}

	render_checkout_preview_html(preview) {
		const overage_row =
			preview.overage_minutes > 0
				? `<div class="fci-info-row fci-info-late">
						<i class="fa fa-exclamation-triangle"></i>
						<span class="fci-info-label">${__("Overage")}:</span>
						<span class="fci-info-value">${preview.overage_minutes} ${__("min")} (${format_currency(preview.overage_charge)})</span>
					</div>`
				: `<div class="fci-info-row">
						<i class="fa fa-check-circle"></i>
						<span class="fci-info-value">${__("No overage - on time.")}</span>
					</div>`;

		return `
			<div class="fci-card-info">
				<div class="fci-info-row">
					<i class="fa fa-map-marker"></i>
					<span class="fci-info-label">${__("Facility")}:</span>
					<span class="fci-info-value">${frappe.utils.escape_html(preview.facility_name || "")}</span>
				</div>
				${
					preview.check_in_time
						? `<div class="fci-info-row">
								<i class="fa fa-sign-in"></i>
								<span class="fci-info-label">${__("Checked in at")}:</span>
								<span class="fci-info-value">${sc_fci_short_datetime(preview.check_in_time)}</span>
							</div>`
						: ""
				}
				${
					preview.actual_duration != null
						? `<div class="fci-info-row">
								<i class="fa fa-hourglass-half"></i>
								<span class="fci-info-label">${__("Duration so far")}:</span>
								<span class="fci-info-value">${preview.actual_duration} ${__("min")}</span>
							</div>`
						: ""
				}
				${overage_row}
			</div>
		`;
	}

	show_check_out_dialog(facility_booking, preview) {
		// Staff can review/adjust the check-out time before confirming - every
		// edit re-runs get_checkout_preview against the edited time (same
		// arithmetic as the eventual submit) so the overage shown always
		// matches what will actually be billed.
		const recalculate = frappe.utils.debounce((dialog, as_of) => {
			if (!as_of) return;
			frappe.call({
				method: "sports_complex.sports_complex.page.facility_checkin.facility_checkin.get_checkout_preview",
				args: { facility_booking, as_of },
				callback: (r) => {
					if (r.message) {
						dialog.fields_dict.preview.$wrapper.html(this.render_checkout_preview_html(r.message));
					}
				},
			});
		}, 400);

		const dialog = new frappe.ui.Dialog({
			title: __("Check Out {0}", [preview.customer || facility_booking]),
			fields: [
				{
					fieldtype: "HTML",
					fieldname: "preview",
					options: this.render_checkout_preview_html(preview),
				},
				{
					fieldtype: "Datetime",
					fieldname: "check_out_time",
					label: __("Check-Out Time"),
					default: preview.as_of || frappe.datetime.now_datetime(),
					reqd: 1,
					onchange: () => recalculate(dialog, dialog.get_value("check_out_time")),
				},
			],
			primary_action_label: __("Confirm Check Out"),
			primary_action: (values) => {
				dialog.hide();
				this.do_check_out(facility_booking, values.check_out_time);
			},
		});

		dialog.show();
	}

	do_check_out(facility_booking, check_out_time) {
		frappe.call({
			method: "sports_complex.sports_complex.page.facility_checkin.facility_checkin.check_out_booking",
			args: { facility_booking, check_out_time },
			freeze: true,
			freeze_message: __("Checking out..."),
			callback: (r) => {
				if (r.message && r.message.status === "Success") {
					const overage = r.message.overage_charge;
					frappe.show_alert({
						message: overage
							? __("Checked out - overage charge {0}", [format_currency(overage)])
							: __("Checked out"),
						indicator: "green",
					});
					this.refresh_all();
				}
			},
			error: (err) => {
				if (!(err && err._server_messages)) {
					frappe.show_alert({ message: __("Check-out failed"), indicator: "red" });
				}
			},
		});
	}

	open_book_facility_dialog() {
		const dialog = new frappe.ui.Dialog({
			title: __("Book a Facility"),
			size: "large",
			fields: [
				{
					fieldtype: "Link",
					fieldname: "facility",
					options: "Sports Facility",
					label: __("Facility"),
					reqd: 1,
					get_query: () => ({ filters: { status: "Active" } }),
					onchange: () => this.refresh_booking_slots(dialog),
				},
				{ fieldtype: "Column Break" },
				{
					fieldtype: "Date",
					fieldname: "booking_date",
					label: __("Date"),
					default: frappe.datetime.get_today(),
					reqd: 1,
					onchange: () => this.refresh_booking_slots(dialog),
				},
				{ fieldtype: "Section Break" },
				{
					// Plain HTML rather than a MultiSelect control - staff are
					// choosing from a short, fully-known list of open slots
					// for one facility/date (not typing/searching against an
					// open-ended set), so a bank of click-to-toggle chips
					// reads faster than a dropdown, and lets several
					// (including non-adjacent) slots be picked for one
					// booking trip in one pass. Selection state lives in
					// dialog._selected_slots (see render_slot_picker) since
					// an HTML field has no get_value() of its own.
					fieldtype: "HTML",
					fieldname: "slot_picker",
					label: __("Available Time Slots"),
				},
				{ fieldtype: "Section Break" },
				{
					fieldtype: "Link",
					fieldname: "customer",
					options: "Customer",
					label: __("Customer"),
					reqd: 1,
				},
				{ fieldtype: "Section Break" },
				{
					fieldtype: "Small Text",
					fieldname: "notes",
					label: __("Notes"),
				},
			],
			primary_action_label: __("Book Facility"),
			primary_action: (values) => {
				const selected = dialog._selected_slots ? Array.from(dialog._selected_slots.values()) : [];
				if (!selected.length) {
					frappe.show_alert({ message: __("Select at least one available time slot"), indicator: "orange" });
					return;
				}
				dialog.hide();
				this.do_book_facility({
					customer: values.customer,
					notes: values.notes,
					slots: selected.map((slot) => ({
						sports_facility: values.facility,
						booking_date: values.booking_date,
						start_time: slot.start_time,
						end_time: slot.end_time,
					})),
				});
			},
		});

		dialog._selected_slots = new Map();
		this.render_slot_picker(dialog, null);
		dialog.show();
	}

	render_slot_picker(dialog, slots) {
		const $wrapper = dialog.fields_dict.slot_picker.$wrapper;

		if (slots === null) {
			$wrapper.html(`<p class="text-muted">${__("Pick a facility and date to see open slots")}</p>`);
			return;
		}
		if (!slots.length) {
			$wrapper.html(`<p class="text-muted">${__("No open slots for this facility on this date")}</p>`);
			return;
		}

		const chips = slots
			.map((s) => {
				const key = `${s.start_time}|${s.end_time}`;
				const selected = dialog._selected_slots.has(key);
				const label = `${sc_fci_short_time(s.start_time)} - ${sc_fci_short_time(s.end_time)}`;
				return `
					<div class="fci-slot-chip${selected ? " selected" : ""}" data-key="${frappe.utils.escape_html(key)}">
						${label}
					</div>
				`;
			})
			.join("");

		$wrapper.html(`
			<div class="fci-slot-picker-header">
				<span>${__("{0} slot(s) available", [slots.length])}</span>
				<a class="fci-slot-select-all">${__("Select all")}</a>
			</div>
			<div class="fci-slot-picker-grid">${chips}</div>
		`);

		$wrapper.find(".fci-slot-chip").on("click", (e) => {
			const $chip = $(e.currentTarget);
			const key = $chip.attr("data-key");
			if (dialog._selected_slots.has(key)) {
				dialog._selected_slots.delete(key);
				$chip.removeClass("selected");
			} else {
				const slot = slots.find((s) => `${s.start_time}|${s.end_time}` === key);
				dialog._selected_slots.set(key, slot);
				$chip.addClass("selected");
			}
		});

		$wrapper.find(".fci-slot-select-all").on("click", () => {
			// Toggles as a set: fills every slot in if any are still
			// unselected, otherwise (all already selected) clears them all -
			// so the same link works as both "select all" and "clear" without
			// needing two separate controls.
			const all_selected = slots.every((s) => dialog._selected_slots.has(`${s.start_time}|${s.end_time}`));
			if (all_selected) {
				dialog._selected_slots.clear();
			} else {
				slots.forEach((s) => dialog._selected_slots.set(`${s.start_time}|${s.end_time}`, s));
			}
			this.render_slot_picker(dialog, slots);
		});
	}

	refresh_booking_slots(dialog) {
		const facility = dialog.get_value("facility");
		const booking_date = dialog.get_value("booking_date");

		dialog._selected_slots = new Map();

		if (!facility || !booking_date) {
			this.render_slot_picker(dialog, null);
			return;
		}

		dialog.fields_dict.slot_picker.$wrapper.html(`<p class="text-muted">${__("Loading available slots...")}</p>`);

		frappe.call({
			method: "sports_complex.sports_complex.doctype.facility_booking.facility_booking.get_available_slots",
			args: { sports_facility: facility, date: booking_date },
			callback: (r) => {
				// Drop a stale response if the user already changed
				// facility/date again (or the dialog moved on) before this
				// landed - otherwise a slow first request finishing after a
				// faster second one would clobber the slot list with the
				// wrong facility/date's data.
				if (dialog.get_value("facility") !== facility || dialog.get_value("booking_date") !== booking_date) {
					return;
				}
				this.render_slot_picker(dialog, r.message || []);
			},
		});
	}

	do_book_facility(args) {
		frappe.call({
			method: "sports_complex.sports_complex.doctype.facility_booking.facility_booking.create_staff_booking_cart",
			args,
			freeze: true,
			freeze_message: __("Booking..."),
			callback: (r) => {
				if (r.message && r.message.bookings) {
					frappe.show_alert({
						message: __("{0} booking(s) created ({1})", [r.message.bookings.length, r.message.booking_status]),
						indicator: "green",
					});
					// New bookings may land on today's/this facility's board
					// right away (e.g. Confirmed for a same-day slot) - reload
					// both queues so they show up without a manual refresh.
					this.refresh_all();
				}
			},
			error: (err) => {
				if (!(err && err._server_messages)) {
					frappe.show_alert({ message: __("Booking failed"), indicator: "red" });
				}
			},
		});
	}

	// "All Bookings" panel - the two queues above only ever show
	// Confirmed/Checked-In bookings (all either queue can act on), so a
	// booking sitting on Payment Pending, Draft, Completed, Cancelled or
	// No-show is otherwise invisible anywhere on this page. This dialog
	// is a read/lookup view honouring the board's own current filters
	// (facility/date/customer/booking) - not a replacement for Facility
	// Booking's own list view, which is still where staff would go for
	// reporting, editing, or anything past 200 rows.
	open_all_bookings_dialog() {
		const dialog = new frappe.ui.Dialog({
			title: __("All Bookings"),
			size: "extra-large",
			fields: [{ fieldtype: "HTML", fieldname: "bookings_table" }],
		});
		dialog.show();
		this.load_all_bookings(dialog);
	}

	load_all_bookings(dialog) {
		const $wrapper = dialog.fields_dict.bookings_table.$wrapper;
		$wrapper.html(`<p class="text-muted">${__("Loading...")}</p>`);

		frappe.call({
			method: "sports_complex.sports_complex.page.facility_checkin.facility_checkin.get_all_bookings",
			args: this.get_common_args(),
			callback: (r) => {
				this.render_all_bookings_table(dialog, r.message || []);
			},
		});
	}

	render_all_bookings_table(dialog, bookings) {
		const $wrapper = dialog.fields_dict.bookings_table.$wrapper;

		if (!bookings.length) {
			$wrapper.html(`
				<div class="fci-empty-state">
					<i class="fa fa-inbox"></i>
					<p>${__("No bookings match the current filters")}</p>
				</div>
			`);
			return;
		}

		const rows = bookings
			.map((b) => {
				let action = "";
				if (b.booking_status === "Payment Pending") {
					// No "Mark Paid & Confirm" shortcut here any more - it used
					// to flip this booking's own status fields without ever
					// creating a Payment Entry, leaving its Sales Invoice
					// sitting Unpaid. Real payment collection lives on the
					// Cashier page, which creates and submits one before
					// touching the booking's status - see this file's own
					// toolbar comment above for the fuller story.
					action = `<button class="btn btn-outline-primary btn-sm fci-btn-action fci-ab-collect-btn" data-booking="${b.name}">${__("Collect Payment")}</button>`;
				} else if (b.booking_status === "Confirmed") {
					action = `<button class="btn btn-success btn-sm fci-btn-action fci-ab-checkin-btn" data-booking="${b.name}">${__("Check In")}</button>`;
				} else if (b.booking_status === "Checked-In") {
					action = `<button class="btn btn-primary btn-sm fci-btn-action fci-ab-checkout-btn" data-booking="${b.name}">${__("Check Out")}</button>`;
				}

				return `
					<tr>
						<td><strong>${frappe.utils.escape_html(b.name)}</strong></td>
						<td>${frappe.utils.escape_html(b.customer || "")}</td>
						<td>${frappe.utils.escape_html(b.facility_name || "")}</td>
						<td>${frappe.datetime.str_to_user(b.booking_date)}</td>
						<td>${sc_fci_short_time(b.start_time)} - ${sc_fci_short_time(b.end_time)}</td>
						<td>${format_currency(b.total_amount)}</td>
						<td>${sc_fci_status_badge(b.booking_status)}</td>
						<td>${frappe.utils.escape_html(b.payment_status || "-")}</td>
						<td>${action}</td>
					</tr>
				`;
			})
			.join("");

		$wrapper.html(`
			<div class="fci-scrollable-content" style="max-height: 60vh;">
				<table class="fci-all-bookings-table">
					<thead>
						<tr>
							<th>${__("ID")}</th>
							<th>${__("Customer")}</th>
							<th>${__("Facility")}</th>
							<th>${__("Date")}</th>
							<th>${__("Time")}</th>
							<th>${__("Amount")}</th>
							<th>${__("Status")}</th>
							<th>${__("Payment")}</th>
							<th></th>
						</tr>
					</thead>
					<tbody>${rows}</tbody>
				</table>
			</div>
		`);

		$wrapper.find(".fci-ab-collect-btn").on("click", () => {
			dialog.hide();
			frappe.set_route("cashier", "facility");
		});
		$wrapper.find(".fci-ab-checkin-btn").on("click", (e) => {
			dialog.hide();
			this.open_check_in_dialog($(e.currentTarget).attr("data-booking"));
		});
		$wrapper.find(".fci-ab-checkout-btn").on("click", (e) => {
			dialog.hide();
			this.open_check_out_dialog($(e.currentTarget).attr("data-booking"));
		});
	}

}

function sc_fci_short_time(value) {
	if (!value) return "";
	const parsed = moment(value, ["HH:mm:ss", "HH:mm"]);
	return parsed.isValid() ? parsed.format("h:mm A") : value;
}

function sc_fci_short_datetime(value) {
	if (!value) return "";
	const parsed = moment(value);
	return parsed.isValid() ? parsed.format("MMM D, h:mm A") : value;
}

function sc_fci_status_badge(status) {
	// Covers every Facility Booking.booking_status value, not just the
	// Confirmed/Checked-In ones the two live queues already render their
	// own badges for (fci-status-confirmed/fci-status-checkedin, defined
	// alongside these classes) - the "All Bookings" panel is the one
	// place on this page every status can show up.
	const classes = {
		Draft: "fci-status-draft",
		"Payment Pending": "fci-status-payment-pending",
		Confirmed: "fci-status-confirmed",
		"Checked-In": "fci-status-checkedin",
		Completed: "fci-status-completed",
		Cancelled: "fci-status-cancelled",
		"No-show": "fci-status-noshow",
	};
	const cls = classes[status] || "fci-status-draft";
	return `<span class="fci-status-badge ${cls}">${frappe.utils.escape_html(__(status || ""))}</span>`;
}
