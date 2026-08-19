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
		this.payment_methods = [];

		this.page.set_secondary_action(__('Refresh'), () => this.load(), 'refresh');

		this.$wrapper = $(`
			<div class="trc-wrapper">
				<div class="trc-summary"></div>
				<div class="trc-columns">
					<div class="trc-column">
						<h5>${__('Awaiting Registration Fee')}</h5>
						<div class="trc-list" data-list="awaiting_bill">
							<div class="trc-empty">${__('Loading...')}</div>
						</div>
					</div>
					<div class="trc-column">
						<h5>${__('Awaiting Payment')}</h5>
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
			.trc-wrapper { padding: 10px 5px 30px; max-width: 1200px; margin: 0 auto; }
			.trc-summary { margin-bottom: 15px; color: var(--text-muted); font-size: 13px; }
			.trc-columns { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
			@media (max-width: 900px) { .trc-columns { grid-template-columns: 1fr; } }
			.trc-column h5 { font-weight: 600; margin-bottom: 10px; }
			.trc-list { display: flex; flex-direction: column; gap: 10px; }
			.trc-empty { color: var(--text-muted); padding: 15px; text-align: center; border: 1px dashed var(--border-color); border-radius: 8px; }
			.trc-card { border: 1px solid var(--border-color); border-radius: 10px; padding: 14px; background: var(--card-bg, #fff); }
			.trc-card .trc-name { font-weight: 600; font-size: 14px; }
			.trc-card .trc-meta { color: var(--text-muted); font-size: 12px; margin-top: 2px; }
			.trc-card .trc-row { display: flex; justify-content: space-between; align-items: center; margin-top: 10px; }
			.trc-card .trc-amount { font-weight: 600; font-size: 15px; }
			.trc-card .trc-outstanding { color: var(--red-500, #d1435b); }
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
				this.render_summary();
			},
		});

		frappe.call({
			method: 'sports_complex.sports_complex.page.trial_registration_cashier.trial_registration_cashier.get_billing_queue',
			freeze: true,
			callback: (r) => {
				const data = r.message || {};
				this.render_awaiting_bill(data.awaiting_bill || []);
				this.render_awaiting_payment(data.awaiting_payment || []);
			},
		});
	}

	render_summary() {
		const currency = frappe.defaults.get_global_default('currency');
		this.$wrapper.find('.trc-summary').html(
			this.fee > 0
				? __('Trial Registration Fee: {0}', [format_currency(this.fee, currency)])
				: `<span style="color:var(--red-500,#d1435b)">${__(
						'No Trial Registration Fee is configured - set one under Sports Complex Setup > Trials before billing trialists.'
					)}</span>`
		);
	}

	render_awaiting_bill(rows) {
		const $list = this.$wrapper.find('[data-list="awaiting_bill"]').empty();
		if (!rows.length) {
			$list.append(`<div class="trc-empty">${__('Nobody waiting to be billed')}</div>`);
			return;
		}
		rows.forEach((t) => {
			const $card = $(`
				<div class="trc-card">
					<div class="trc-name">${frappe.utils.escape_html(t.full_name)}</div>
					<div class="trc-meta">${frappe.utils.escape_html(t.name)}
						${t.trial_batch ? ' &middot; ' + frappe.utils.escape_html(t.trial_batch) : ''}
						${t.sport ? ' &middot; ' + frappe.utils.escape_html(t.sport) : ''}
					</div>
					<div class="trc-meta">${__('Cleared')}: ${t.medical_cleared_on ? frappe.datetime.str_to_user(t.medical_cleared_on) : '-'}</div>
					<div class="trc-row">
						<span class="trc-amount">${format_currency(this.fee, frappe.defaults.get_global_default('currency'))}</span>
						<button class="btn btn-primary btn-sm trc-bill-btn">${__('Create Bill')}</button>
					</div>
				</div>
			`);
			$card.find('.trc-bill-btn').on('click', () => this.create_bill(t, $card));
			$list.append($card);
		});
	}

	render_awaiting_payment(rows) {
		const $list = this.$wrapper.find('[data-list="awaiting_payment"]').empty();
		if (!rows.length) {
			$list.append(`<div class="trc-empty">${__('No outstanding registration bills')}</div>`);
			return;
		}
		rows.forEach((t) => {
			const $card = $(`
				<div class="trc-card">
					<div class="trc-name">${frappe.utils.escape_html(t.full_name)}</div>
					<div class="trc-meta">${frappe.utils.escape_html(t.name)}
						${t.trial_batch ? ' &middot; ' + frappe.utils.escape_html(t.trial_batch) : ''}
					</div>
					<div class="trc-meta">
						<a href="/app/sales-invoice/${encodeURIComponent(t.registration_invoice)}" target="_blank">
							${frappe.utils.escape_html(t.registration_invoice)}
						</a>
					</div>
					<div class="trc-row">
						<span class="trc-amount trc-outstanding">${format_currency(t.outstanding_amount, t.currency)}</span>
						<button class="btn btn-primary btn-sm trc-pay-btn">${__('Collect Payment')}</button>
					</div>
				</div>
			`);
			$card.find('.trc-pay-btn').on('click', () => this.collect_payment(t));
			$list.append($card);
		});
	}

	create_bill(trialist, $card) {
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
