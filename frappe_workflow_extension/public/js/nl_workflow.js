$(document).on("form-refresh", function (event, frm) {
	if (!frm || !frm.doctype) return;
	if (frm.doc.__islocal) return;

	try {
		frappe.call({
			method: "frappe_workflow_extension.frappe_workflow_extension.workflow.has_workflow",
			args: { doctype: frm.doctype },
			callback: function (res) {
				const workflow_name = res.message;

				const has_workflow = !!workflow_name;
				if (has_workflow) {
					frm.page.clear_primary_action();
					override_document_status(frm);
				}

				if (workflow_name) {
					load_allowed_transitions(frm, workflow_name);
				}
			},
		});
	} catch (error) {
		console.error(" Error initializing workflow:", error);
	}
});

function load_allowed_transitions(frm, workflow_name) {
	frappe.call({
		method: "frappe_workflow_extension.frappe_workflow_extension.workflow.get_transitions",
		args: { doc: frm.doc, workflow: workflow_name },
		callback: function (r) {
			const transitions = r.message || [];
			frm.page.clear_actions_menu();

			if (!transitions.length) return;

			let added = false;

			transitions.forEach((t) => {
				frm.page.add_action_item(__(t.action), function () {
					frappe.dom.freeze();
					frm.selected_workflow_action = t.action;

					if (!frappe.ui.form.check_mandatory(frm)) {
						return frappe.dom.unfreeze();
					}

					frappe
						.xcall(
							"frappe_workflow_extension.frappe_workflow_extension.workflow.apply_workflow",
							{
								doc: frm.doc,
								action: t.action,
							}
						)
						.then((doc) => {
							frappe.model.sync(doc);
							frm.refresh();
							frm.selected_workflow_action = null;
							frappe.show_alert({
								message: __("Workflow action applied: {0}", [t.action]),
								indicator: "green",
							});
						})
						.finally(() => frappe.dom.unfreeze());
				});

				added = true;
			});

			if (added) add_workflow_help_action(frm, transitions);
		},
	});
}

function add_workflow_help_action(frm, transitions) {
	try {
		frm.page.add_action_item(__("Workflow Help"), function () {
			const state_field = frappe.workflow.get_state_fieldname(frm.doctype);
			const current_state = frm.doc[state_field] || __("Unknown");

			let next_actions = transitions
				.map((d) => `${d.action.bold()} (${d.allowed})`)
				.join(", ");

			if (!next_actions) next_actions = __("None: End of Workflow").bold();

			const dialog = new frappe.ui.Dialog({
				title: __("Workflow: {0}", [frm.doctype]),
				fields: [
					{
						fieldtype: "HTML",
						fieldname: "info",
						options: `
							<p>${__("Current status")}: ${current_state.bold()}</p>
							<p>${__("Next actions")}: ${next_actions}</p>
							<p>${__("Only users with permission can perform these transitions.")}</p>
						`,
					},
				],
			});
			dialog.show();
		});
	} catch (error) {
		console.warn(" Failed to add help action:", error);
	}
}

function override_document_status(frm) {
	try {
		const state_field = frappe.workflow.get_state_fieldname(frm.doctype);
		const current_state = frm.doc[state_field];
		let status_label = "";
		let color = "gray";
		if (frm.doc.docstatus === 0) {
			status_label = __("Draft");
			color = "gray";
		} else if (frm.doc.docstatus === 1) {
			status_label = current_state ? __(current_state) : __("Submitted");
			color = "blue";
		} else if (frm.doc.docstatus === 2) {
			status_label = __("Cancelled");
			color = "red";
		}
		if (frm.page && frm.page.set_indicator) {
			frm.page.set_indicator(status_label, color);
		}
	} catch (error) {
		console.warn(" Failed to override document status:", error);
	}
}
