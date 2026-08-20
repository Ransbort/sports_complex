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
// Visual language deliberately borrows Frappe desk's own primitives (icon
// sprite via frappe.utils.icon(), indicator-pill colors, CSS custom
// properties like --border-color/--text-muted/--card-bg) rather than a
// separate palette, so this reads as part of the desk rather than an
// embedded foreign widget.

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

		this.page.set_secondary_action(__('Refresh'), () => this.load(), 'refresh-cw');

		this.$wrapper = $(`
			<div class="trc-wrapper">
				<div class="trc-stats"></div>
				<div class="trc-columns">
					<div class="trc-column">
						<div class="trc-column-head">
							<span class="trc-column-title">
								${frappe.utils.icon('user-plus', 'sm')}
								${__('Awaiting Registration Fee')}
							</span>
							<span class="trc-count-pill" data-count="awaiting_bill">0</span>
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
							<span class="trc-count-pill" data-count="awaiting_payment">0</span>
						</div>
						<div class="trc-list" data-list="awaiting_payment">
							<div class="trc-empty">${__('Loading...')}</div>
						</div>
					</div>
				</div>
			</div>
		`).appendTo(this.page.main);

		this.inject_styles();
		this.bind_realtime();
		this.load();
	}

	inject_styles() {
		if ($('#trc-styles').length) return;
		$(`<style id="trc-styles">
			.trc-wrapper { padding: 6px 2px 30px; max-width: 1240px; margin: 0 auto; }

			/* ---------- summary stat tiles ---------- */
			.trc-stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; margin-bottom: 24px; }
			@media (max-width: 900px) { .trc-stats { grid-template-columns: 1fr; } }
			.trc-stat { border: 1px solid var(--border-color); border-radius: 10px; background: var(--card-bg, var(--fg-color)); padding: 16px 18px; display: flex; align-items: flex-start; gap: 12px; }
			.trc-stat-icon { width: 34px; height: 34px; border-radius: 8px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
			.trc-stat-icon svg { width: 16px; height: 16px; }
			.trc-stat-icon.trc-icon-neutral { background: var(--gray-100, #f4f5f6); color: var(--text-muted); }
			.trc-stat-icon.trc-icon-good { background: var(--green-100, #ddf4e4); color: var(--green-600, #16794c); }
			.trc-stat-icon.trc-icon-warning { background: var(--yellow-100, #fdf3d7); color: var(--yellow-700, #9c6f00); }
			.trc-stat-body { min-width: 0; }
			.trc-stat-label { font-size: 12px; color: var(--text-muted); font-weight: 500; text-transform: uppercase; letter-spacing: 0.03em; }
			.trc-stat-value { font-size: 22px; font-weight: 700; color: var(--text-color); line-height: 1.3; margin-top: 2px; }
			.trc-stat-sub { font-size: 12px; color: var(--text-muted); margin-top: 2px; }
			.trc-stat-warn-text { color: var(--yellow-700, #9c6f00); }

			/* ---------- columns ---------- */
			.trc-columns { display: grid; grid-template-columns: 1fr 1fr; gap: 22px; align-items: start; }
			@media (max-width: 900px) { .trc-columns { grid-template-columns: 1fr; } }
			.trc-column-head { display: flex; align-items: center; justify-content: space-between; padding-bottom: 8px; margin-bottom: 12px; border-bottom: 1px solid var(--border-color); }
			.trc-column-title { display: flex; align-items: center; gap: 8px; font-weight: 600; font-size: 13.5px; color: var(--text-color); }
			.trc-column-title svg { width: 14px; height: 14px; color: var(--text-muted); }
			.trc-count-pill { min-width: 22px; height: 20px; padding: 0 7px; border-radius: 10px; background: var(--gray-100, #f4f5f6); color: var(--text-muted); font-size: 11.5px; font-weight: 600; display: inline-flex; align-items: center; justify-content: center; }

			.trc-list { display: flex; flex-direction: column; gap: 10px; }
			.trc-empty { display: flex; flex-direction: column; align-items: center; gap: 8px; color: var(--text-muted); padding: 34px 15px; text-align: center; border: 1px dashed var(--border-color); border-radius: 10px; font-size: 12.5px; }
			.trc-empty svg { width: 20px; height: 20px; opacity: 0.55; }

			/* ---------- cards ---------- */
			.trc-card { border: 1px solid var(--border-color); border-radius: 10px; padding: 14px 16px; background: var(--card-bg, var(--fg-color)); transition: box-shadow .12s ease, border-color .12s ease; }
			.trc-card:hover { box-shadow: var(--shadow-sm, 0 1px 3px rgba(0,0,0,.08)); border-color: var(--dark-border-color, var(--border-color)); }
			.trc-card-top { display: flex; align-items: flex-start; gap: 10px; }
			.trc-avatar { width: 34px; height: 34px; border-radius: 50%; background: var(--blue-100, #d7e7fb); color: var(--blue-600, #1450a3); font-size: 12.5px; font-weight: 700; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
			.trc-card-id { min-width: 0; flex: 1; }
			.trc-name { font-weight: 600; font-size: 14px; color: var(--text-color); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
			.trc-meta { color: var(--text-muted); font-size: 12px; margin-top: 1px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
			.trc-tags { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
			.trc-tag { display: inline-flex; align-items: center; gap: 4px; font-size: 11px; padding: 2px 8px; border-radius: 5px; background: var(--gray-100, #f4f5f6); color: var(--text-muted); font-weight: 500; }
			.trc-tag svg { width: 11px; height: 11px; }
			.trc-tag-cleared { background: var(--green-100, #ddf4e4); color: var(--green-700, #106b3e); }
			.trc-invoice-link { display: inline-flex; align-items: center; gap: 4px; font-size: 11px; padding: 2px 8px; border-radius: 5px; background: var(--blue-100, #d7e7fb); color: var(--blue-600, #1450a3); font-weight: 500; text-decoration: none; }
			.trc-invoice-link:hover { text-decoration: underline; }
			.trc-invoice-link svg { width: 11px; height: 11px; }

			.trc-card-foot { display: flex; align-items: center; justify-content: space-between; margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--border-color); }
			.trc-amount-block { display: flex; flex-direction: column; }
			.trc-amount-label { font-size: 10.5px; text-transform: uppercase; letter-spacing: 0.03em; color: var(--text-muted); }
			.trc-amount { font-weight: 700; font-size: 16px; color: var(--text-color); }
			.trc-amount-outstanding { color: var(--yellow-700, #9c6f00); }

			.trc-btn { display: inline-flex; align-items: center; gap: 6px; }
			.trc-btn svg { width: 13px; height: 13px; }

			/* ---------- misc ---------- */
			.trc-fee-warning { display: flex; align-items: center; gap: 8px; padding: 10px 14px; border-radius: 8px; background: var(--yellow-100, #fdf3d7); color: var(--yellow-700, #9c6f00); font-size: 12.5px; margin-bottom: 18px; }
			.trc-fee-warning svg { width: 15px; height: 15px; flex-shrink: 0; }
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

		const tiles = [
			{
				icon: 'dollar-sign',
				tone: 'neutral',
				label: __('Trial Registration Fee'),
				value: this.fee > 0 ? format_currency(this.fee, this.currency) : '—',
				sub: this.fee > 0 ? __('per trialist') : __('not configured'),
			},
			{
				icon: 'user-plus',
				tone: 'neutral',
				label: __('Awaiting Bill'),
				value: String(awaiting_bill.length),
				sub: __('cleared, not yet invoiced'),
			},
			{
				icon: 'credit-card',
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
				<div class="trc-stat">
					<span class="trc-stat-icon trc-icon-${t.tone}">${frappe.utils.icon(t.icon, 'sm')}</span>
					<div class="trc-stat-body">
						<div class="trc-stat-label">${t.label}</div>
						<div class="trc-stat-value">${t.value}</div>
						<div class="trc-stat-sub">${t.sub}</div>
					</div>
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
						<button class="btn btn-primary btn-sm trc-btn trc-bill-btn" ${this.fee > 0 ? '' : 'disabled'}>
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
						<button class="btn btn-primary btn-sm trc-btn trc-pay-btn">
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
