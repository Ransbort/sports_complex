// Copyright (c) 2026, Sports Complex and contributors
// For license information, please see license.txt
//
// Trial Registration Cashier - a scoped-down sibling of Healthcare's own
// Cashier Portal (healthcare/healthcare/page/cashier_portal/cashier_portal.js),
// built for one job: once a doctor clears a trialist
// (Trialist.medical_clearance_status == "Cleared"), let front-of-house staff
// raise a bill for the Trial Registration Fee and collect payment on it -
// see trial_registration_cashier.py for the backend and
// doctype/trialist/trialist.py's create_registration_invoice() for the bill
// itself.
//
// Visual language matches Facility Check-In (sports_complex/sports_complex/
// page/facility_checkin/facility_checkin.js) - its sidebar sibling and the
// other front-desk tool in this app: icon-badge toolbar, colored stat tiles,
// bordered card queues, viewport-bound layout (flex + min-height: 0 so each
// queue scrolls in its own space instead of the page growing past the
// screen). Frappe desk CSS custom properties (--border-color/--text-muted/
// --card-bg) are still used for anything that should just follow desk theme
// (borders, muted text, card backgrounds) rather than being hardcoded.

frappe.pages['trial-registration-cashier'].on_page_load = function (wrapper) {
	let page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __('Trial Registration Cashier'),
		single_column: true,
	});

	new TrialRegistrationCashier(page);
};

class TrialRegistrationCashier {
	constructor(page) {
		this.page = page;
		this.fee = 0;
		this.currency = frappe.defaults.get_global_default('currency');
		this.payment_methods = [];

		// Facility Check-In keeps its own toolbar refresh button rather than
		// Frappe's page-level secondary action, so this does the same - see
		// the click handler bound after append below.
		this.$wrapper = $(`
			<div class="trc-wrapper">
				<div class="trc-top-section">
					<div class="trc-toolbar">
						<div class="trc-toolbar-title">
							<div class="trc-icon-badge">${frappe.utils.icon('dollar-sign', 'md')}</div>
							<div>
								<h4>${__('Trial Registration Cashier')}</h4>
								<div class="trc-toolbar-subtitle">${__('Bill and collect trial registration fees for cleared trialists')}</div>
							</div>
						</div>
						<div class="trc-toolbar-actions">
							<button class="trc-btn-icon" id="trc-refresh-btn" title="${__('Refresh')}">
								${frappe.utils.icon('refresh-cw', 'sm')}
							</button>
						</div>
					</div>
					<div class="trc-stats"></div>
				</div>
				<div class="trc-columns">
					<div class="trc-column">
						<div class="trc-column-head">
							<span class="trc-column-title">
								${frappe.utils.icon('user-plus', 'sm')}
								${__('Awaiting Registration Fee')}
							</span>
							<span class="trc-count-pill trc-count-pill-info" data-count="awaiting_bill">0</span>
						</div>
						<div class="trc-list" data-list="awaiting_bill">
							<div class="trc-empty">${__('Loading...')}</div>
						</div>
					</div>
					<div class="trc-column">
						<div class="trc-column-head">
							<span class="trc-column-title">
								${frappe.utils.icon('credit-card', 'sm')}
								${__('Awaiting Payment')}
							</span>
							<span class="trc-count-pill trc-count-pill-warning" data-count="awaiting_payment">0</span>
						</div>
						<div class="trc-list" data-list="awaiting_payment">
							<div class="trc-empty">${__('Loading...')}</div>
						</div>
					</div>
				</div>
			</div>
		`).appendTo(this.page.main);

		this.$wrapper.find('#trc-refresh-btn').on('click', () => this.load());

		this.inject_styles();
		this.bind_realtime();
		this.load();
	}

	inject_styles() {
		if ($('#trc-styles').length) return;
		$(`<style id="trc-styles">
			/* Same viewport-bound shape as Facility Check-In's .fci-wrapper -
			   fixed to the screen instead of growing with content, with
			   flex: 1 / min-height: 0 down the chain so .trc-list is always
			   exactly the space left over, however tall the header renders.
			   See facility_checkin.js for the fuller explanation of why that
			   matters (a fixed max-height guess there used to let cards spill
			   past the panel instead of scrolling inside it). */
			.trc-wrapper {
				height: calc(100vh - 60px);
				box-sizing: border-box;
				display: flex;
				flex-direction: column;
				padding: 20px;
				max-width: 1400px;
				margin: 0 auto;
				overflow: hidden;
			}

			.trc-top-section { flex-shrink: 0; }

			/* ---------- toolbar ---------- */
			.trc-toolbar {
				display: flex;
				justify-content: space-between;
				align-items: center;
				padding-bottom: 16px;
				margin-bottom: 16px;
				border-bottom: 1px solid var(--border-color);
			}
			.trc-toolbar-title { display: flex; align-items: center; gap: 12px; }
			.trc-toolbar-title .trc-icon-badge {
				width: 40px; height: 40px; border-radius: 10px;
				background: #f0f1fe; color: var(--primary-color);
				display: flex; align-items: center; justify-content: center;
				flex-shrink: 0;
			}
			.trc-icon-badge svg { width: 18px; height: 18px; }
			.trc-toolbar-title h4 { margin: 0; font-size: 1.2rem; font-weight: 700; color: var(--text-color); line-height: 1.3; }
			.trc-toolbar-title .trc-toolbar-subtitle { font-size: 0.83rem; color: var(--text-muted); margin-top: 1px; }
			.trc-toolbar-actions { display: flex; align-items: center; gap: 10px; }
			.trc-btn-icon {
				width: 38px; height: 38px; border-radius: 8px;
				border: 1px solid var(--border-color); background: var(--card-bg, var(--fg-color));
				color: var(--text-color);
				display: flex; align-items: center; justify-content: center;
				cursor: pointer; transition: all .15s ease;
			}
			.trc-btn-icon svg { width: 15px; height: 15px; }
			.trc-btn-icon:hover { background: var(--gray-100, #f4f5f6); border-color: var(--primary-color); color: var(--primary-color); }

			/* ---------- summary stat tiles ---------- */
			.trc-stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin: 16px 0; }
			@media (max-width: 900px) { .trc-stats { grid-template-columns: 1fr; } }
			.trc-stat-tile {
				background: var(--card-bg, var(--fg-color));
				border: 1px solid var(--border-color);
				border-radius: 10px;
				padding: 14px 16px;
				box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
			}
			.trc-stat-label { font-size: 0.78rem; color: var(--text-muted); font-weight: 500; margin-bottom: 4px; }
			.trc-stat-value { font-size: 1.35rem; font-weight: 700; color: var(--text-color); }
			.trc-stat-sub { font-size: 0.75rem; color: var(--text-muted); margin-top: 2px; }
			.trc-stat-tile.stat-blue .trc-stat-value { color: #667eea; }
			.trc-stat-tile.stat-orange .trc-stat-value { color: #fd7e14; }
			.trc-stat-tile.stat-green .trc-stat-value { color: #28a745; }

			/* ---------- columns ---------- */
			.trc-columns {
				flex: 1;
				min-height: 0;
				display: grid;
				grid-template-columns: 1fr 1fr;
				gap: 20px;
				overflow: hidden;
			}
			@media (max-width: 900px) {
				.trc-columns { grid-template-columns: 1fr; overflow-y: auto; overflow-x: hidden; }
				.trc-column { max-height: 50vh; }
			}

			.trc-column {
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

			.trc-column-head {
				flex-shrink: 0;
				display: flex; align-items: center; justify-content: space-between;
				padding-bottom: 12px; margin-bottom: 14px;
				border-bottom: 2px solid var(--primary-color);
			}
			.trc-column-title { display: flex; align-items: center; gap: 8px; font-weight: 600; font-size: 1rem; color: var(--text-color); }
			.trc-column-title svg { width: 14px; height: 14px; color: var(--text-muted); }
			.trc-count-pill { min-width: 22px; height: 22px; padding: 0 8px; border-radius: 10px; font-size: 0.8rem; font-weight: 600; display: inline-flex; align-items: center; justify-content: center; }
			.trc-count-pill-info { background: #cfe2ff; color: #084298; }
			.trc-count-pill-warning { background: #fff3cd; color: #856404; }

			.trc-list {
				flex: 1;
				min-height: 0;
				overflow-y: auto;
				overflow-x: hidden;
				padding-right: 6px;
				display: flex;
				flex-direction: column;
				gap: 10px;
			}
			.trc-list::-webkit-scrollbar { width: 8px; }
			.trc-list::-webkit-scrollbar-track { background: #f1f1f1; border-radius: 4px; }
			.trc-list::-webkit-scrollbar-thumb { background: #ccc; border-radius: 4px; }
			.trc-list::-webkit-scrollbar-thumb:hover { background: #aaa; }

			.trc-empty { display: flex; flex-direction: column; align-items: center; gap: 8px; color: var(--text-muted); padding: 40px 20px; text-align: center; font-size: 0.92rem; }
			.trc-empty svg { width: 42px; height: 42px; opacity: 0.3; }

			/* ---------- cards ---------- */
			.trc-card {
				border: 2px solid #e0e0e0;
				border-radius: 12px;
				padding: 16px;
				background: var(--card-bg, var(--fg-color));
				transition: all 0.3s ease;
				box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
			}
			.trc-card:hover {
				border-color: var(--primary-color);
				box-shadow: 0 4px 16px rgba(102, 126, 234, 0.2);
				transform: translateY(-2px);
			}
			.trc-card-top {
				display: flex; align-items: flex-start; gap: 10px;
				padding-bottom: 12px; margin-bottom: 12px;
				border-bottom: 1px solid var(--border-color);
			}
			.trc-avatar {
				width: 34px; height: 34px; border-radius: 50%;
				background: #f0f1fe; color: var(--primary-color);
				font-size: 12.5px; font-weight: 700;
				display: flex; align-items: center; justify-content: center; flex-shrink: 0;
			}
			.trc-card-id { min-width: 0; flex: 1; }
			.trc-name { font-weight: 700; font-size: 1.05rem; color: var(--text-color); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
			.trc-meta { color: var(--text-muted); font-size: 0.85rem; margin-top: 1px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
			.trc-tags { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 2px; }
			.trc-tag {
				display: inline-flex; align-items: center; gap: 4px;
				font-size: 0.72rem; font-weight: 600; padding: 4px 10px; border-radius: 12px;
				background: var(--gray-100, #f4f5f6); color: var(--text-muted);
				text-transform: uppercase;
			}
			.trc-tag svg { width: 11px; height: 11px; }
			.trc-tag-cleared { background: #cfe2ff; color: #084298; text-transform: none; padding: 5px 11px; border-radius: 8px; font-size: 0.8rem; }
			.trc-invoice-link {
				display: inline-flex; align-items: center; gap: 4px;
				font-size: 0.75rem; padding: 4px 10px; border-radius: 12px;
				background: #f0f1fe; color: var(--primary-color); font-weight: 600; text-decoration: none;
			}
			.trc-invoice-link:hover { text-decoration: underline; }
			.trc-invoice-link svg { width: 11px; height: 11px; }

			.trc-card-foot { display: flex; align-items: center; justify-content: space-between; margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--border-color); }
			.trc-amount-block { display: flex; flex-direction: column; }
			.trc-amount-label { font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.03em; color: var(--text-muted); }
			.trc-amount { font-weight: 700; font-size: 1.05rem; color: var(--text-color); }
			.trc-amount-outstanding { color: #856404; }

			.trc-btn { padding: 7px 14px; font-size: 0.85rem; font-weight: 600; border-radius: 8px; display: inline-flex; align-items: center; gap: 6px; }
			.trc-btn svg { width: 13px; height: 13px; }

			/* ---------- misc ---------- */
			.trc-fee-warning { display: flex; align-items: center; gap: 8px; padding: 10px 14px; border-radius: 8px; background: #fff3cd; color: #856404; font-size: 0.85rem; margin-bottom: 16px; }
			.trc-fee-warning svg { width: 15px; height: 15px; flex-shrink: 0; }

			@media (max-width: 768px) {
				.trc-wrapper { padding: 15px; }
				.trc-toolbar { flex-direction: column; align-items: flex-start; gap: 12px; }
				.trc-toolbar-actions { width: 100%; justify-content: flex-end; }
			}
		</style>`).appendTo('head');
	}

	bind_realtime() {
		// Fired by healthcare_integration.py's _propagate_to_patient() /
		// _propagate_to_trialist() the moment a doctor clears a trialist -
		// refresh so newly-cleared trialists show up here without a manual
		// refresh. Also react to our own events (create_registration_invoice()
		// / create_payment_entry() below) so a second cashier's screen
		// stays in sync.
		['trial_candidate_medically_cleared', 'trialist_medical_cleared',
			'trial_registration_invoiced', 'trial_registration_fee_paid'].forEach((event) => {
			frappe.realtime.on(event, (data) => {
				frappe.show_alert({ message: data.message, indicator: 'blue' }, 5);
				this.load();
			});
		});
	}

	load() {
		frappe.call({
			method: 'sports_complex.sports_complex.page.trial_registration_cashier.trial_registration_cashier.get_trial_registration_fee',
			callback: (r) => {
				this.fee = flt(r.message);
				this.render_stats();
			},
		});

		frappe.call({
			method: 'sports_complex.sports_complex.page.trial_registration_cashier.trial_registration_cashier.get_billing_queue',
			freeze: true,
			callback: (r) => {
				const data = r.message || {};
				this.awaiting_bill = data.awaiting_bill || [];
				this.awaiting_payment = data.awaiting_payment || [];
				this.render_stats();
				this.render_awaiting_bill(this.awaiting_bill);
				this.render_awaiting_payment(this.awaiting_payment);
			},
		});
	}

	render_stats() {
		const awaiting_bill = this.awaiting_bill || [];
		const awaiting_payment = this.awaiting_payment || [];
		const outstanding_total = awaiting_payment.reduce((sum, t) => sum + flt(t.outstanding_amount), 0);

		// tone -> the same stat-tile color language as Facility Check-In's
		// blue/orange/green tiles: blue for a plain informational number,
		// orange for something that wants attention without being urgent,
		// green for "nothing outstanding, all clear".
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

		const $stats = this.$wrapper.find('.trc-stats').empty();
		tiles.forEach((t) => {
			$stats.append(`
				<div class="trc-stat-tile ${TONE_CLASS[t.tone] || 'stat-blue'}">
					<div class="trc-stat-label">${t.label}</div>
					<div class="trc-stat-value">${t.value}</div>
					<div class="trc-stat-sub">${t.sub}</div>
				</div>
			`);
		});

		let $warning = this.$wrapper.find('.trc-fee-warning');
		if (this.fee <= 0) {
			if (!$warning.length) {
				$warning = $(`<div class="trc-fee-warning">
					${frappe.utils.icon('alert-circle', 'sm')}
					<span></span>
				</div>`).insertBefore(this.$wrapper.find('.trc-stats'));
			}
			$warning.find('span').text(
				__('No Trial Registration Fee is configured - set one under Sports Complex Setup > Trials before billing trialists.')
			);
		} else {
			$warning.remove();
		}
	}

	render_awaiting_bill(rows) {
		this.$wrapper.find('[data-count="awaiting_bill"]').text(rows.length);
		const $list = this.$wrapper.find('[data-list="awaiting_bill"]').empty();
		if (!rows.length) {
			$list.append(`<div class="trc-empty">${frappe.utils.icon('inbox', 'md')}${__('Nobody waiting to be billed')}</div>`);
			return;
		}
		rows.forEach((t) => {
			const $card = $(`
				<div class="trc-card">
					<div class="trc-card-top">
						<div class="trc-avatar">${this.initials(t.full_name)}</div>
						<div class="trc-card-id">
							<div class="trc-name" title="${frappe.utils.escape_html(t.full_name)}">${frappe.utils.escape_html(t.full_name)}</div>
							<div class="trc-meta">${frappe.utils.escape_html(t.name)}</div>
						</div>
					</div>
					<div class="trc-tags">
						<span class="trc-tag trc-tag-cleared">${frappe.utils.icon('check', 'xs')}${__('Cleared')} ${t.medical_cleared_on ? frappe.datetime.str_to_user(t.medical_cleared_on) : ''}</span>
						${t.trial_batch ? `<span class="trc-tag">${frappe.utils.escape_html(t.trial_batch)}</span>` : ''}
						${t.sport ? `<span class="trc-tag">${frappe.utils.escape_html(t.sport)}</span>` : ''}
					</div>
					<div class="trc-card-foot">
						<div class="trc-amount-block">
							<span class="trc-amount-label">${__('Fee')}</span>
							<span class="trc-amount">${format_currency(this.fee, this.currency)}</span>
						</div>
						<button class="btn btn-primary trc-btn trc-bill-btn" ${this.fee > 0 ? '' : 'disabled'}>
							${frappe.utils.icon('file-text', 'xs')}${__('Create Bill')}
						</button>
					</div>
				</div>
			`);
			$card.find('.trc-bill-btn').on('click', () => this.create_bill(t));
			$list.append($card);
		});
	}

	render_awaiting_payment(rows) {
		this.$wrapper.find('[data-count="awaiting_payment"]').text(rows.length);
		const $list = this.$wrapper.find('[data-list="awaiting_payment"]').empty();
		if (!rows.length) {
			$list.append(`<div class="trc-empty">${frappe.utils.icon('inbox', 'md')}${__('No outstanding registration bills')}</div>`);
			return;
		}
		rows.forEach((t) => {
			const $card = $(`
				<div class="trc-card">
					<div class="trc-card-top">
						<div class="trc-avatar">${this.initials(t.full_name)}</div>
						<div class="trc-card-id">
							<div class="trc-name" title="${frappe.utils.escape_html(t.full_name)}">${frappe.utils.escape_html(t.full_name)}</div>
							<div class="trc-meta">${frappe.utils.escape_html(t.name)}${t.trial_batch ? ' · ' + frappe.utils.escape_html(t.trial_batch) : ''}</div>
						</div>
					</div>
					<div class="trc-tags">
						<a class="trc-invoice-link" href="/app/sales-invoice/${encodeURIComponent(t.registration_invoice)}" target="_blank">
							${frappe.utils.icon('file-text', 'xs')}${frappe.utils.escape_html(t.registration_invoice)}
						</a>
					</div>
					<div class="trc-card-foot">
						<div class="trc-amount-block">
							<span class="trc-amount-label">${__('Outstanding')}</span>
							<span class="trc-amount trc-amount-outstanding">${format_currency(t.outstanding_amount, t.currency)}</span>
						</div>
						<button class="btn btn-primary trc-btn trc-pay-btn">
							${frappe.utils.icon('credit-card', 'xs')}${__('Collect Payment')}
						</button>
					</div>
				</div>
			`);
			$card.find('.trc-pay-btn').on('click', () => this.collect_payment(t));
			$list.append($card);
		});
	}

	initials(full_name) {
		if (!full_name) return '?';
		const parts = full_name.trim().split(/\s+/);
		const chars = parts.length > 1 ? [parts[0][0], parts[parts.length - 1][0]] : [parts[0][0]];
		return chars.join('').toUpperCase();
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
							this.load();
						}
					},
				});
			}
		);
	}

	collect_payment(trialist) {
		if (!this.payment_methods.length) {
			frappe.call({
				method: 'sports_complex.sports_complex.page.trial_registration_cashier.trial_registration_cashier.get_payment_methods',
				callback: (r) => {
					this.payment_methods = (r.message || []).map((m) => m.name);
					this.show_payment_dialog(trialist);
				},
			});
		} else {
			this.show_payment_dialog(trialist);
		}
	}

	show_payment_dialog(trialist) {
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
					method: 'sports_complex.sports_complex.page.trial_registration_cashier.trial_registration_cashier.create_payment_entry',
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
							this.load();
						}
					},
				});
			},
		});
		dialog.show();
	}

	print_receipt(invoice_name) {
		frappe.call({
			method: 'sports_complex.sports_complex.page.trial_registration_cashier.trial_registration_cashier.get_print_content',
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
}
