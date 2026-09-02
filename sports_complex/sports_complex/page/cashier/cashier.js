// Copyright (c) 2026, Sports Complex and contributors
// For license information, please see license.txt
//
// Unified Cashier - collapses what used to be two separate desk pages,
// Trial Registration Cashier (page/trial_registration_cashier, now just a
// redirect stub - see that page's own on_page_load) and Facility Check-In's
// payment-collection duties, into one till front-of-house staff work from
// for both kinds of outstanding payment. A tab switcher (Trial
// Registrations / Facility Bookings) swaps between two otherwise-
// independent sections rather than trying to force both billing flows
// into one shared queue shape - they don't share one: trial registration
// bills are raised on demand from a "cleared" queue, Facility Bookings
// already carry their own invoice the moment they're created, so there's
// no "awaiting bill" step to show on that side at all.
//
// Visual language still traces back to Healthcare's own Cashier Portal
// (healthcare/healthcare/page/cashier_portal/cashier_portal.js) by way of
// trial_registration_cashier.js, whose CSS this reuses near-verbatim under
// a "csh-" prefix (was "trc-") - same icon-badge toolbar, colored stat
// tiles, bordered card queues, viewport-bound layout (flex + min-height: 0
// so each queue scrolls in its own space instead of the page growing past
// the screen - see that file's own comment for the fuller "why" this
// matters). Facility Check-In (sports_complex/sports_complex/page/
// facility_checkin/facility_checkin.js) shares the same shape too, under
// its own "fci-" prefix - all three pages read as one visual family.

frappe.pages['cashier'].on_page_load = function (wrapper) {
	let page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __('Cashier'),
		single_column: true,
	});

	// Facility Check-In's own "Cashier" toolbar button deep-links here via
	// frappe.set_route('cashier', 'facility') so a staff member sent to
	// collect payment for a specific booking lands straight on that tab
	// instead of the Trial Registrations one - see facility_checkin.js.
	const initial_tab = frappe.get_route()[1] === 'facility' ? 'facility' : 'trial';
	new SportsComplexCashier(page, initial_tab);

	hide_desk_breadcrumbs();
};

// This page reads as its own full-bleed screen (own icon-badge title, own
// toolbar) - the desk's usual "Home / Cashier" breadcrumb strip above it
// is redundant chrome eating vertical space for no benefit here (there's
// no drill-down hierarchy to retrace - Cashier is one flat page, not a
// child of some list view). Unlike this page's own .csh-wrapper, that
// breadcrumb strip is a persistent, global element the router reuses
// across every route rather than one scoped to this page, so it has to
// be explicitly hidden on arrival (on_page_load for the first visit,
// on_page_show for every visit after - Frappe only re-runs on_page_load
// once per session) and explicitly restored the moment any *other* route
// becomes active, or leaving Cashier would carry the hidden state with it
// into every other page for the rest of the session.
function hide_desk_breadcrumbs() {
	// Covers both the id this element has carried across recent Frappe
	// versions and the older class-based container, so this doesn't quietly
	// stop working on a version this wasn't tested against - hiding a
	// selector that matches nothing is a harmless no-op either way.
	$('#navbar-breadcrumbs, .page-head .breadcrumb-container').hide();
}

frappe.pages['cashier'].on_page_show = hide_desk_breadcrumbs;

if (!frappe.router.__csh_breadcrumb_restore_bound) {
	frappe.router.on('change', () => {
		if (frappe.get_route()[0] !== 'cashier') {
			$('#navbar-breadcrumbs, .page-head .breadcrumb-container').show();
		}
	});
	frappe.router.__csh_breadcrumb_restore_bound = true;
}

class SportsComplexCashier {
	constructor(page, initial_tab = 'trial') {
		this.page = page;
		this.activeTab = initial_tab;
		this.fee = 0;
		this.currency = frappe.defaults.get_global_default('currency');
		this.payment_methods = [];
		this.facility_filters = { facility: null, date: null, customer: '' };
		this.facility_bookings = [];

		this.$wrapper = $(`
			<div class="csh-wrapper">
				<div class="csh-top-section">
					<div class="csh-toolbar">
						<div class="csh-toolbar-title">
							<div class="csh-icon-badge">${frappe.utils.icon('dollar-sign', 'md')}</div>
							<div>
								<h4>${__('Cashier')}</h4>
								<div class="csh-toolbar-subtitle">${__('Collect payment for trial registrations and facility bookings')}</div>
							</div>
						</div>
						<div class="csh-toolbar-actions">
							<div class="csh-tab-group">
								<button class="csh-tab-btn${this.activeTab === 'trial' ? ' active' : ''}" data-tab="trial">
									${frappe.utils.icon('user-plus', 'sm')} ${__('Trial Registrations')}
								</button>
								<button class="csh-tab-btn${this.activeTab === 'facility' ? ' active' : ''}" data-tab="facility">
									${frappe.utils.icon('calendar', 'sm')} ${__('Facility Bookings')}
								</button>
							</div>
							<button class="csh-btn-icon" id="csh-refresh-btn" title="${__('Refresh')}">
								${frappe.utils.icon('refresh-cw', 'sm')}
							</button>
						</div>
					</div>

					<div class="csh-facility-filters" data-section="facility" style="display: ${this.activeTab === 'facility' ? 'grid' : 'none'};">
						<div class="frappe-control" data-fieldname="facility"></div>
						<div class="frappe-control" data-fieldname="date"></div>
						<div class="frappe-control" data-fieldname="customer"></div>
						<button class="btn btn-default" id="csh-clear-filters-btn">${__('Clear Filters')}</button>
					</div>

					<div class="csh-stats"></div>
				</div>

				<div class="csh-section" data-section="trial" style="display: ${this.activeTab === 'trial' ? 'flex' : 'none'};">
					<div class="csh-columns">
						<div class="csh-column">
							<div class="csh-column-head">
								<span class="csh-column-title">
									${frappe.utils.icon('user-plus', 'sm')}
									${__('Awaiting Registration Fee')}
								</span>
								<span class="csh-count-pill csh-count-pill-info" data-count="awaiting_bill">0</span>
							</div>
							<div class="csh-list" data-list="awaiting_bill">
								<div class="csh-empty">${__('Loading...')}</div>
							</div>
						</div>
						<div class="csh-column">
							<div class="csh-column-head">
								<span class="csh-column-title">
									${frappe.utils.icon('credit-card', 'sm')}
									${__('Awaiting Payment')}
								</span>
								<span class="csh-count-pill csh-count-pill-warning" data-count="awaiting_payment">0</span>
							</div>
							<div class="csh-list" data-list="awaiting_payment">
								<div class="csh-empty">${__('Loading...')}</div>
							</div>
						</div>
					</div>
				</div>

				<div class="csh-section" data-section="facility" style="display: ${this.activeTab === 'facility' ? 'flex' : 'none'};">
					<div class="csh-columns csh-columns-single">
						<div class="csh-column">
							<div class="csh-column-head">
								<span class="csh-column-title">
									${frappe.utils.icon('credit-card', 'sm')}
									${__('Pending Payments')}
								</span>
								<span class="csh-count-pill csh-count-pill-warning" data-count="facility_pending">0</span>
							</div>
							<div class="csh-list csh-list-grid" data-list="facility_pending">
								<div class="csh-empty">${__('Loading...')}</div>
							</div>
						</div>
					</div>
				</div>
			</div>
		`).appendTo(this.page.main);

		this.$wrapper.find('#csh-refresh-btn').on('click', () => this.load_active_tab());
		this.$wrapper.find('.csh-tab-btn').on('click', (e) => this.switch_tab($(e.currentTarget).attr('data-tab')));

		this.inject_styles();
		this.setup_facility_filters();
		this.bind_realtime();
		this.load_active_tab();
	}

	switch_tab(tab) {
		if (tab === this.activeTab) return;
		this.activeTab = tab;

		this.$wrapper.find('.csh-tab-btn').removeClass('active');
		this.$wrapper.find(`.csh-tab-btn[data-tab="${tab}"]`).addClass('active');
		this.$wrapper.find('.csh-section').hide();
		this.$wrapper.find(`.csh-section[data-section="${tab}"]`).show();
		this.$wrapper.find('.csh-facility-filters').toggle(tab === 'facility');

		this.load_active_tab();
	}

	load_active_tab() {
		if (this.activeTab === 'trial') {
			this.load_trial();
		} else {
			this.load_facility();
		}
	}

	inject_styles() {
		if ($('#csh-styles').length) return;
		$(`<style id="csh-styles">
			/* Same viewport-bound shape as Facility Check-In's .fci-wrapper and
			   Trial Registration Cashier's own .trc-wrapper (this page's direct
			   ancestor) - fixed to the screen instead of growing with content,
			   with flex: 1 / min-height: 0 down the chain so .csh-list is
			   always exactly the space left over, however tall the header
			   renders. See facility_checkin.js for the fuller explanation of
			   why that matters. */
			.csh-wrapper {
				height: calc(100vh - 60px);
				box-sizing: border-box;
				display: flex;
				flex-direction: column;
				padding: 20px;
				max-width: 1400px;
				margin: 0 auto;
				overflow: hidden;
			}

			.csh-top-section { flex-shrink: 0; }

			/* ---------- toolbar ---------- */
			.csh-toolbar {
				display: flex;
				justify-content: space-between;
				align-items: center;
				padding-bottom: 16px;
				margin-bottom: 16px;
				border-bottom: 1px solid var(--border-color);
				flex-wrap: wrap;
				gap: 12px;
			}
			.csh-toolbar-title { display: flex; align-items: center; gap: 12px; }
			.csh-toolbar-title .csh-icon-badge {
				width: 40px; height: 40px; border-radius: 10px;
				background: #f0f1fe; color: var(--primary-color);
				display: flex; align-items: center; justify-content: center;
				flex-shrink: 0;
			}
			.csh-icon-badge svg { width: 18px; height: 18px; }
			.csh-toolbar-title h4 { margin: 0; font-size: 1.2rem; font-weight: 700; color: var(--text-color); line-height: 1.3; }
			.csh-toolbar-title .csh-toolbar-subtitle { font-size: 0.83rem; color: var(--text-muted); margin-top: 1px; }
			.csh-toolbar-actions { display: flex; align-items: center; gap: 10px; }

			.csh-tab-group {
				display: flex;
				gap: 4px;
				border: 1px solid var(--border-color);
				border-radius: 8px;
				padding: 3px;
				background: var(--gray-100, #f4f5f6);
			}
			.csh-tab-btn {
				display: flex; align-items: center; gap: 6px;
				border: none; background: transparent;
				padding: 6px 12px; border-radius: 6px;
				font-size: 0.83rem; font-weight: 600; color: var(--text-muted);
				cursor: pointer; transition: all 0.15s ease;
			}
			.csh-tab-btn svg { width: 13px; height: 13px; }
			.csh-tab-btn:hover { color: var(--primary-color); }
			.csh-tab-btn.active { background: var(--card-bg, var(--fg-color)); color: var(--primary-color); box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1); }

			.csh-btn-icon {
				width: 38px; height: 38px; border-radius: 8px;
				border: 1px solid var(--border-color); background: var(--card-bg, var(--fg-color));
				color: var(--text-color);
				display: flex; align-items: center; justify-content: center;
				cursor: pointer; transition: all .15s ease;
			}
			.csh-btn-icon svg { width: 15px; height: 15px; }
			.csh-btn-icon:hover { background: var(--gray-100, #f4f5f6); border-color: var(--primary-color); color: var(--primary-color); }

			/* ---------- facility filter bar ---------- */
			.csh-facility-filters {
				display: grid;
				grid-template-columns: 1fr 1fr 1fr auto;
				gap: 14px;
				align-items: end;
				background: var(--card-bg, var(--fg-color));
				border: 1px solid var(--border-color);
				border-radius: 12px;
				padding: 16px 16px 12px;
				margin-bottom: 4px;
			}
			.csh-facility-filters .form-group { margin-bottom: 0; }

			/* ---------- summary stat tiles ---------- */
			.csh-stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin: 16px 0; }
			@media (max-width: 900px) { .csh-stats { grid-template-columns: 1fr; } }
			.csh-stat-tile {
				background: var(--card-bg, var(--fg-color));
				border: 1px solid var(--border-color);
				border-radius: 10px;
				padding: 14px 16px;
				box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
			}
			.csh-stat-label { font-size: 0.78rem; color: var(--text-muted); font-weight: 500; margin-bottom: 4px; }
			.csh-stat-value { font-size: 1.35rem; font-weight: 700; color: var(--text-color); }
			.csh-stat-sub { font-size: 0.75rem; color: var(--text-muted); margin-top: 2px; }
			.csh-stat-tile.stat-blue .csh-stat-value { color: #667eea; }
			.csh-stat-tile.stat-orange .csh-stat-value { color: #fd7e14; }
			.csh-stat-tile.stat-green .csh-stat-value { color: #28a745; }

			/* ---------- section / columns ---------- */
			.csh-section { flex: 1; min-height: 0; display: flex; flex-direction: column; overflow: hidden; }
			.csh-columns {
				flex: 1;
				min-height: 0;
				display: grid;
				grid-template-columns: 1fr 1fr;
				gap: 20px;
				overflow: hidden;
			}
			.csh-columns-single { grid-template-columns: 1fr; }
			@media (max-width: 900px) {
				.csh-columns { grid-template-columns: 1fr; overflow-y: auto; overflow-x: hidden; }
				.csh-column { max-height: 50vh; }
				.csh-facility-filters { grid-template-columns: 1fr; }
			}

			.csh-column {
				background: var(--card-bg, var(--fg-color));
				border: 1px solid var(--border-color);
				border-radius: 12px;
				box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
				padding: 16px;
				display: flex;
				flex-direction: column;
				min-height: 0;
				overflow: hidden;
			}

			.csh-column-head {
				flex-shrink: 0;
				display: flex; align-items: center; justify-content: space-between;
				padding-bottom: 12px; margin-bottom: 14px;
				border-bottom: 2px solid var(--primary-color);
			}
			.csh-column-title { display: flex; align-items: center; gap: 8px; font-weight: 600; font-size: 1rem; color: var(--text-color); }
			.csh-column-title svg { width: 14px; height: 14px; color: var(--text-muted); }
			.csh-count-pill { min-width: 22px; height: 22px; padding: 0 8px; border-radius: 10px; font-size: 0.8rem; font-weight: 600; display: inline-flex; align-items: center; justify-content: center; }
			.csh-count-pill-info { background: #cfe2ff; color: #084298; }
			.csh-count-pill-warning { background: #fff3cd; color: #856404; }

			.csh-list {
				flex: 1;
				min-height: 0;
				overflow-y: auto;
				overflow-x: hidden;
				padding-right: 6px;
				display: flex;
				flex-direction: column;
				gap: 10px;
			}
			.csh-list-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; align-content: start; }
			.csh-list::-webkit-scrollbar { width: 8px; }
			.csh-list::-webkit-scrollbar-track { background: #f1f1f1; border-radius: 4px; }
			.csh-list::-webkit-scrollbar-thumb { background: #ccc; border-radius: 4px; }
			.csh-list::-webkit-scrollbar-thumb:hover { background: #aaa; }

			.csh-empty { display: flex; flex-direction: column; align-items: center; gap: 8px; color: var(--text-muted); padding: 40px 20px; text-align: center; font-size: 0.92rem; grid-column: 1 / -1; }
			.csh-empty svg { width: 42px; height: 42px; opacity: 0.3; }

			/* ---------- cards ---------- */
			.csh-card {
				border: 2px solid #e0e0e0;
				border-radius: 12px;
				padding: 16px;
				background: var(--card-bg, var(--fg-color));
				transition: all 0.3s ease;
				box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
			}
			.csh-card:hover {
				border-color: var(--primary-color);
				box-shadow: 0 4px 16px rgba(102, 126, 234, 0.2);
				transform: translateY(-2px);
			}
			.csh-card-top {
				display: flex; align-items: flex-start; gap: 10px;
				padding-bottom: 12px; margin-bottom: 12px;
				border-bottom: 1px solid var(--border-color);
			}
			.csh-avatar {
				width: 34px; height: 34px; border-radius: 50%;
				background: #f0f1fe; color: var(--primary-color);
				font-size: 12.5px; font-weight: 700;
				display: flex; align-items: center; justify-content: center; flex-shrink: 0;
			}
			.csh-card-id { min-width: 0; flex: 1; }
			.csh-name { font-weight: 700; font-size: 1.05rem; color: var(--text-color); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
			.csh-meta { color: var(--text-muted); font-size: 0.85rem; margin-top: 1px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
			.csh-tags { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 2px; }
			.csh-tag {
				display: inline-flex; align-items: center; gap: 4px;
				font-size: 0.72rem; font-weight: 600; padding: 4px 10px; border-radius: 12px;
				background: var(--gray-100, #f4f5f6); color: var(--text-muted);
				text-transform: uppercase;
			}
			.csh-tag svg { width: 11px; height: 11px; }
			.csh-tag-cleared { background: #cfe2ff; color: #084298; text-transform: none; padding: 5px 11px; border-radius: 8px; font-size: 0.8rem; }
			.csh-tag-status { text-transform: none; padding: 5px 11px; border-radius: 8px; font-size: 0.8rem; }
			.csh-tag-status-payment-pending { background: #ffe8cc; color: #9c5500; }
			.csh-tag-status-confirmed { background: #cfe2ff; color: #084298; }
			.csh-tag-status-checked-in { background: #fff3cd; color: #856404; }
			.csh-invoice-link {
				display: inline-flex; align-items: center; gap: 4px;
				font-size: 0.75rem; padding: 4px 10px; border-radius: 12px;
				background: #f0f1fe; color: var(--primary-color); font-weight: 600; text-decoration: none;
			}
			.csh-invoice-link:hover { text-decoration: underline; }
			.csh-invoice-link svg { width: 11px; height: 11px; }

			.csh-card-foot { display: flex; align-items: center; justify-content: space-between; margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--border-color); }
			.csh-amount-block { display: flex; flex-direction: column; }
			.csh-amount-label { font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.03em; color: var(--text-muted); }
			.csh-amount { font-weight: 700; font-size: 1.05rem; color: var(--text-color); }
			.csh-amount-outstanding { color: #856404; }

			.csh-btn { padding: 7px 14px; font-size: 0.85rem; font-weight: 600; border-radius: 8px; display: inline-flex; align-items: center; gap: 6px; }
			.csh-btn svg { width: 13px; height: 13px; }

			/* ---------- misc ---------- */
			.csh-fee-warning { display: flex; align-items: center; gap: 8px; padding: 10px 14px; border-radius: 8px; background: #fff3cd; color: #856404; font-size: 0.85rem; margin-bottom: 16px; }
			.csh-fee-warning svg { width: 15px; height: 15px; flex-shrink: 0; }

			@media (max-width: 768px) {
				.csh-wrapper { padding: 15px; }
				.csh-toolbar { flex-direction: column; align-items: flex-start; gap: 12px; }
				.csh-toolbar-actions { width: 100%; justify-content: space-between; }
			}
		</style>`).appendTo('head');
	}

	bind_realtime() {
		// Fired by healthcare_integration.py's _propagate_to_trialist() the
		// moment a doctor clears a trialist - refresh so newly-cleared
		// trialists show up here without a manual refresh. Also react to our
		// own events (create_bill()/collect_trial_payment() below) so a
		// second cashier's screen stays in sync. Only re-fetches the trial
		// section - none of these events describe a Facility Booking change.
		['trial_candidate_medically_cleared', 'trialist_medical_cleared',
			'trial_registration_invoiced', 'trial_registration_fee_paid'].forEach((event) => {
			frappe.realtime.on(event, (data) => {
				frappe.show_alert({ message: data.message, indicator: 'blue' }, 5);
				if (this.activeTab === 'trial') this.load_trial();
			});
		});
	}

	initials(full_name) {
		if (!full_name) return '?';
		const parts = full_name.trim().split(/\s+/);
		const chars = parts.length > 1 ? [parts[0][0], parts[parts.length - 1][0]] : [parts[0][0]];
		return chars.join('').toUpperCase();
	}

	print_receipt(invoice_name) {
		frappe.call({
			method: 'sports_complex.sports_complex.page.cashier.cashier.get_print_content',
			args: { doctype: 'Sales Invoice', docname: invoice_name },
			callback: (r) => {
				if (!r.message || !r.message.html) return;
				const win = window.open('', '_blank');
				if (!win) return;
				win.document.write(r.message.html);
				win.document.close();
			},
		});
	}

	get_payment_methods(callback) {
		if (this.payment_methods.length) {
			callback();
			return;
		}
		frappe.call({
			method: 'sports_complex.sports_complex.page.cashier.cashier.get_payment_methods',
			callback: (r) => {
				this.payment_methods = (r.message || []).map((m) => m.name);
				callback();
			},
		});
	}

	// =====================================================================
	// Trial Registrations section
	// =====================================================================

	load_trial() {
		frappe.call({
			method: 'sports_complex.sports_complex.page.cashier.cashier.get_trial_registration_fee',
			callback: (r) => {
				this.fee = flt(r.message);
				this.render_trial_stats();
			},
		});

		frappe.call({
			method: 'sports_complex.sports_complex.page.cashier.cashier.get_trial_billing_queue',
			freeze: true,
			callback: (r) => {
				const data = r.message || {};
				this.awaiting_bill = data.awaiting_bill || [];
				this.awaiting_payment = data.awaiting_payment || [];
				this.render_trial_stats();
				this.render_awaiting_bill(this.awaiting_bill);
				this.render_awaiting_payment(this.awaiting_payment);
			},
		});
	}

	render_trial_stats() {
		const awaiting_bill = this.awaiting_bill || [];
		const awaiting_payment = this.awaiting_payment || [];
		const outstanding_total = awaiting_payment.reduce((sum, t) => sum + flt(t.outstanding_amount), 0);

		const TONE_CLASS = { neutral: 'stat-blue', warning: 'stat-orange', good: 'stat-green' };

		const tiles = [
			{
				tone: 'neutral',
				label: __('Trial Registration Fee'),
				value: this.fee > 0 ? format_currency(this.fee, this.currency) : '—',
				sub: this.fee > 0 ? __('per trialist') : __('not configured'),
			},
			{
				tone: 'neutral',
				label: __('Awaiting Bill'),
				value: String(awaiting_bill.length),
				sub: __('cleared, not yet invoiced'),
			},
			{
				tone: awaiting_payment.length ? 'warning' : 'good',
				label: __('Outstanding'),
				value: format_currency(outstanding_total, this.currency),
				sub: awaiting_payment.length
					? __('across {0} bill(s)', [awaiting_payment.length])
					: __('nothing outstanding'),
			},
		];

		this.render_stat_tiles(tiles, TONE_CLASS);

		let $warning = this.$wrapper.find('.csh-fee-warning');
		if (this.fee <= 0) {
			if (!$warning.length) {
				$warning = $(`<div class="csh-fee-warning">
					${frappe.utils.icon('alert-circle', 'sm')}
					<span></span>
				</div>`).insertBefore(this.$wrapper.find('.csh-stats'));
			}
			$warning.find('span').text(
				__('No Trial Registration Fee is configured - set one under Sports Complex Setup > Trials before billing trialists.')
			);
		} else {
			$warning.remove();
		}
	}

	render_stat_tiles(tiles, TONE_CLASS) {
		const $stats = this.$wrapper.find('.csh-stats').empty();
		tiles.forEach((t) => {
			$stats.append(`
				<div class="csh-stat-tile ${TONE_CLASS[t.tone] || 'stat-blue'}">
					<div class="csh-stat-label">${t.label}</div>
					<div class="csh-stat-value">${t.value}</div>
					<div class="csh-stat-sub">${t.sub}</div>
				</div>
			`);
		});
	}

	render_awaiting_bill(rows) {
		this.$wrapper.find('[data-count="awaiting_bill"]').text(rows.length);
		const $list = this.$wrapper.find('[data-list="awaiting_bill"]').empty();
		if (!rows.length) {
			$list.append(`<div class="csh-empty">${frappe.utils.icon('inbox', 'md')}${__('Nobody waiting to be billed')}</div>`);
			return;
		}
		rows.forEach((t) => {
			const $card = $(`
				<div class="csh-card">
					<div class="csh-card-top">
						<div class="csh-avatar">${this.initials(t.full_name)}</div>
						<div class="csh-card-id">
							<div class="csh-name" title="${frappe.utils.escape_html(t.full_name)}">${frappe.utils.escape_html(t.full_name)}</div>
							<div class="csh-meta">${frappe.utils.escape_html(t.name)}</div>
						</div>
					</div>
					<div class="csh-tags">
						<span class="csh-tag csh-tag-cleared">${frappe.utils.icon('check', 'xs')}${__('Cleared')} ${t.medical_cleared_on ? frappe.datetime.str_to_user(t.medical_cleared_on) : ''}</span>
						${t.trial_batch ? `<span class="csh-tag">${frappe.utils.escape_html(t.trial_batch)}</span>` : ''}
						${t.sport ? `<span class="csh-tag">${frappe.utils.escape_html(t.sport)}</span>` : ''}
					</div>
					<div class="csh-card-foot">
						<div class="csh-amount-block">
							<span class="csh-amount-label">${__('Fee')}</span>
							<span class="csh-amount">${format_currency(this.fee, this.currency)}</span>
						</div>
						<button class="btn btn-primary csh-btn csh-bill-btn" ${this.fee > 0 ? '' : 'disabled'}>
							${frappe.utils.icon('file-text', 'xs')}${__('Create Bill')}
						</button>
					</div>
				</div>
			`);
			$card.find('.csh-bill-btn').on('click', () => this.create_bill(t));
			$list.append($card);
		});
	}

	render_awaiting_payment(rows) {
		this.$wrapper.find('[data-count="awaiting_payment"]').text(rows.length);
		const $list = this.$wrapper.find('[data-list="awaiting_payment"]').empty();
		if (!rows.length) {
			$list.append(`<div class="csh-empty">${frappe.utils.icon('inbox', 'md')}${__('No outstanding registration bills')}</div>`);
			return;
		}
		rows.forEach((t) => {
			const $card = $(`
				<div class="csh-card">
					<div class="csh-card-top">
						<div class="csh-avatar">${this.initials(t.full_name)}</div>
						<div class="csh-card-id">
							<div class="csh-name" title="${frappe.utils.escape_html(t.full_name)}">${frappe.utils.escape_html(t.full_name)}</div>
							<div class="csh-meta">${frappe.utils.escape_html(t.name)}${t.trial_batch ? ' · ' + frappe.utils.escape_html(t.trial_batch) : ''}</div>
						</div>
					</div>
					<div class="csh-tags">
						<a class="csh-invoice-link" href="/app/sales-invoice/${encodeURIComponent(t.registration_invoice)}" target="_blank">
							${frappe.utils.icon('file-text', 'xs')}${frappe.utils.escape_html(t.registration_invoice)}
						</a>
					</div>
					<div class="csh-card-foot">
						<div class="csh-amount-block">
							<span class="csh-amount-label">${__('Outstanding')}</span>
							<span class="csh-amount csh-amount-outstanding">${format_currency(t.outstanding_amount, t.currency)}</span>
						</div>
						<button class="btn btn-primary csh-btn csh-pay-btn">
							${frappe.utils.icon('credit-card', 'xs')}${__('Collect Payment')}
						</button>
					</div>
				</div>
			`);
			$card.find('.csh-pay-btn').on('click', () => this.collect_trial_payment(t));
			$list.append($card);
		});
	}

	create_bill(trialist) {
		frappe.confirm(
			__('Raise a Sales Invoice for the trial registration fee against {0}?', [trialist.full_name]),
			() => {
				frappe.call({
					method: 'sports_complex.sports_complex.doctype.trialist.trialist.create_registration_invoice',
					args: { trialist: trialist.name },
					freeze: true,
					freeze_message: __('Creating bill...'),
					callback: (r) => {
						if (r.message && r.message.status === 'Success') {
							frappe.show_alert({
								message: __('Bill {0} created for {1}', [r.message.invoice, trialist.full_name]),
								indicator: 'green',
							}, 6);
							this.load_trial();
						}
					},
				});
			}
		);
	}

	collect_trial_payment(trialist) {
		this.get_payment_methods(() => this.show_trial_payment_dialog(trialist));
	}

	show_trial_payment_dialog(trialist) {
		const dialog = new frappe.ui.Dialog({
			title: __('Collect Registration Fee - {0}', [trialist.full_name]),
			fields: [
				{
					fieldtype: 'HTML',
					options: `<div style="margin-bottom:10px">${__('Outstanding')}: <b>${format_currency(
						trialist.outstanding_amount, trialist.currency
					)}</b></div>`,
				},
				{
					fieldtype: 'Select',
					fieldname: 'mode_of_payment',
					label: __('Mode of Payment'),
					options: this.payment_methods,
					reqd: 1,
					default: this.payment_methods[0],
				},
				{ fieldtype: 'Column Break' },
				{ fieldtype: 'Data', fieldname: 'reference_no', label: __('Reference No') },
				{ fieldtype: 'Date', fieldname: 'reference_date', label: __('Reference Date'), default: 'Today' },
				{ fieldtype: 'Small Text', fieldname: 'remarks', label: __('Remarks') },
			],
			primary_action_label: __('Collect Payment'),
			primary_action: (values) => {
				frappe.call({
					method: 'sports_complex.sports_complex.page.cashier.cashier.create_trial_payment_entry',
					args: {
						invoice_name: trialist.registration_invoice,
						mode_of_payment: values.mode_of_payment,
						remarks: values.remarks,
						reference_no: values.reference_no,
						reference_date: values.reference_date,
					},
					freeze: true,
					freeze_message: __('Recording payment...'),
					callback: (r) => {
						if (r.message && r.message.status === 'Success') {
							dialog.hide();
							frappe.show_alert({
								message: __('Payment {0} recorded for {1}', [r.message.name, trialist.full_name]),
								indicator: 'green',
							}, 6);
							this.print_receipt(trialist.registration_invoice);
							this.load_trial();
						}
					},
				});
			},
		});
		dialog.show();
	}

	// =====================================================================
	// Facility Bookings section
	// =====================================================================

	setup_facility_filters() {
		const $bar = this.$wrapper.find('.csh-facility-filters');

		this.facility_control = frappe.ui.form.make_control({
			parent: $bar.find('[data-fieldname="facility"]'),
			df: {
				fieldtype: 'Link',
				fieldname: 'facility',
				options: 'Sports Facility',
				label: __('Facility'),
				placeholder: __('Filter by facility'),
				get_query: () => ({ filters: { status: 'Active' } }),
				onchange: () => {
					this.facility_filters.facility = this.facility_control.get_value() || null;
					this.load_facility();
				},
			},
			render_input: true,
		});
		this.facility_control.refresh();

		this.date_control = frappe.ui.form.make_control({
			parent: $bar.find('[data-fieldname="date"]'),
			df: {
				fieldtype: 'Date',
				fieldname: 'date',
				label: __('Date'),
				onchange: () => {
					// Same fix as Facility Check-In's own date filter (see
					// facility_checkin.js's setup_filters() for the fuller
					// explanation): write the display text straight to the
					// input instead of routing an empty value back through
					// set_value(), which would re-fire this same onchange
					// handler forever.
					const val = this.date_control.get_value() || '';
					this.date_control.$input.val(val ? frappe.datetime.str_to_user(val) : '');
					this.facility_filters.date = val || null;
					this.load_facility();
				},
			},
			render_input: true,
		});
		this.date_control.refresh();

		this.customer_control = frappe.ui.form.make_control({
			parent: $bar.find('[data-fieldname="customer"]'),
			df: {
				fieldtype: 'Data',
				fieldname: 'customer',
				label: __('Search Customer'),
				placeholder: __('Customer name...'),
			},
			render_input: true,
		});
		this.customer_control.refresh();
		this.customer_control.$input.on('input', frappe.utils.debounce(() => {
			this.facility_filters.customer = this.customer_control.get_value() || '';
			this.load_facility();
		}, 400));

		this.$wrapper.find('#csh-clear-filters-btn').on('click', () => {
			this.facility_control.set_value('');
			this.date_control.set_value('');
			this.customer_control.set_value('');
			this.facility_filters = { facility: null, date: null, customer: '' };
			this.load_facility();
		});
	}

	load_facility() {
		frappe.call({
			method: 'sports_complex.sports_complex.page.cashier.cashier.get_facility_pending_payments',
			args: this.facility_filters,
			freeze: true,
			callback: (r) => {
				this.facility_bookings = r.message || [];
				this.render_facility_stats();
				this.render_facility_list();
			},
		});
	}

	render_facility_stats() {
		const bookings = this.facility_bookings || [];
		const outstanding_total = bookings.reduce((sum, b) => sum + flt(b.outstanding_amount), 0);

		const TONE_CLASS = { neutral: 'stat-blue', warning: 'stat-orange', good: 'stat-green' };
		const payment_pending = bookings.filter((b) => b.booking_status === 'Payment Pending').length;

		const tiles = [
			{
				tone: bookings.length ? 'warning' : 'good',
				label: __('Pending Payments'),
				value: String(bookings.length),
				sub: bookings.length ? __('booking(s) owed money') : __('nothing outstanding'),
			},
			{
				tone: 'neutral',
				label: __('Awaiting Confirmation'),
				value: String(payment_pending),
				sub: __('Payment Pending - not yet Confirmed'),
			},
			{
				tone: bookings.length ? 'warning' : 'good',
				label: __('Outstanding'),
				value: format_currency(outstanding_total, this.currency),
				sub: bookings.length ? __('across {0} booking(s)', [bookings.length]) : __('nothing outstanding'),
			},
		];

		this.render_stat_tiles(tiles, TONE_CLASS);
		this.$wrapper.find('.csh-fee-warning').remove();
	}

	render_facility_list() {
		const bookings = this.facility_bookings || [];
		this.$wrapper.find('[data-count="facility_pending"]').text(bookings.length);
		const $list = this.$wrapper.find('[data-list="facility_pending"]').empty();

		if (!bookings.length) {
			$list.append(`<div class="csh-empty">${frappe.utils.icon('inbox', 'md')}${__('No facility bookings owe payment')}</div>`);
			return;
		}

		const STATUS_CLASS = {
			'Payment Pending': 'csh-tag-status-payment-pending',
			'Confirmed': 'csh-tag-status-confirmed',
			'Checked-In': 'csh-tag-status-checked-in',
		};

		bookings.forEach((b) => {
			const $card = $(`
				<div class="csh-card">
					<div class="csh-card-top">
						<div class="csh-avatar">${this.initials(b.customer)}</div>
						<div class="csh-card-id">
							<div class="csh-name" title="${frappe.utils.escape_html(b.customer || '')}">${frappe.utils.escape_html(b.customer || '')}</div>
							<div class="csh-meta">${frappe.utils.escape_html(b.facility_name || '')} · ${frappe.datetime.str_to_user(b.booking_date)}</div>
						</div>
					</div>
					<div class="csh-tags">
						<span class="csh-tag csh-tag-status ${STATUS_CLASS[b.booking_status] || ''}">${frappe.utils.escape_html(__(b.booking_status || ''))}</span>
						${b.sales_invoice ? `
							<a class="csh-invoice-link" href="/app/sales-invoice/${encodeURIComponent(b.sales_invoice)}" target="_blank">
								${frappe.utils.icon('file-text', 'xs')}${frappe.utils.escape_html(b.sales_invoice)}
							</a>
						` : ''}
					</div>
					<div class="csh-card-foot">
						<div class="csh-amount-block">
							<span class="csh-amount-label">${__('Outstanding')}</span>
							<span class="csh-amount csh-amount-outstanding">${format_currency(b.outstanding_amount, this.currency)}</span>
						</div>
						<button class="btn btn-primary csh-btn csh-pay-btn" ${b.sales_invoice ? '' : 'disabled'}>
							${frappe.utils.icon('credit-card', 'xs')}${__('Collect Payment')}
						</button>
					</div>
				</div>
			`);
			$card.find('.csh-pay-btn').on('click', () => this.collect_facility_payment(b));
			$list.append($card);
		});
	}

	collect_facility_payment(booking) {
		this.get_payment_methods(() => this.show_facility_payment_dialog(booking));
	}

	show_facility_payment_dialog(booking) {
		const dialog = new frappe.ui.Dialog({
			title: __('Collect Payment - {0}', [booking.customer || booking.name]),
			fields: [
				{
					fieldtype: 'HTML',
					options: `<div style="margin-bottom:10px">${__('Outstanding')}: <b>${format_currency(
						booking.outstanding_amount, this.currency
					)}</b></div>`,
				},
				{
					fieldtype: 'Select',
					fieldname: 'mode_of_payment',
					label: __('Mode of Payment'),
					options: this.payment_methods,
					reqd: 1,
					default: this.payment_methods[0],
				},
				{ fieldtype: 'Column Break' },
				{
					fieldtype: 'Currency',
					fieldname: 'paid_amount',
					label: __('Amount'),
					default: booking.outstanding_amount,
					reqd: 1,
					description: __('Partial payments are allowed - the booking stays owing the rest.'),
				},
				{ fieldtype: 'Data', fieldname: 'reference_no', label: __('Reference No') },
				{ fieldtype: 'Column Break' },
				{ fieldtype: 'Date', fieldname: 'reference_date', label: __('Reference Date'), default: 'Today' },
				{ fieldtype: 'Small Text', fieldname: 'remarks', label: __('Remarks') },
			],
			primary_action_label: __('Collect Payment'),
			primary_action: (values) => {
				if (flt(values.paid_amount) <= 0 || flt(values.paid_amount) > flt(booking.outstanding_amount) + 0.01) {
					frappe.show_alert({ message: __('Amount must be between 0 and the outstanding balance'), indicator: 'orange' });
					return;
				}
				frappe.call({
					method: 'sports_complex.sports_complex.page.cashier.cashier.create_facility_payment_entry',
					args: {
						facility_booking: booking.name,
						mode_of_payment: values.mode_of_payment,
						paid_amount: values.paid_amount,
						remarks: values.remarks,
						reference_no: values.reference_no,
						reference_date: values.reference_date,
					},
					freeze: true,
					freeze_message: __('Recording payment...'),
					callback: (r) => {
						if (r.message && r.message.status === 'Success') {
							dialog.hide();
							frappe.show_alert({
								message: __('Payment {0} recorded for {1}', [r.message.name, booking.customer || booking.name]),
								indicator: 'green',
							}, 6);
							this.print_receipt(booking.sales_invoice);
							this.load_facility();
						}
					},
				});
			},
		});
		dialog.show();
	}
}
