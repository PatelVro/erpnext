// Integration Exception form: the triage runbook as a button
// (docs/OPERATIONS.md §3). Plain JS, no build step, no framework — the UI
// only calls the same whitelisted replay used from the console.
frappe.ui.form.on("Integration Exception", {
	refresh(frm) {
		if (frm.is_new() || frm.doc.status === "Ignored") return;
		if (!frm.doc.replay_payload_minimal) return;

		frm.add_custom_button(__("Replay Import"), () => {
			frappe.call({
				method: "canadian_outlet.co_orders.replay.replay_exception",
				args: { exception_name: frm.doc.name },
				freeze: true,
				freeze_message: __("Replaying through the Order Import Service..."),
				callback(r) {
					const res = r.message || {};
					if (res.outcome === "Created" || res.outcome === "Duplicate") {
						frappe.msgprint({
							title: __("Imported"),
							indicator: "green",
							message: __("Outcome: {0} — Sales Order {1}", [
								res.outcome,
								res.sales_order || "",
							]),
						});
					} else {
						frappe.msgprint({
							title: __("Still failing"),
							indicator: "red",
							message: __("Outcome: {0} — see {1}", [
								res.outcome,
								res.integration_exception || frm.doc.name,
							]),
						});
					}
					frm.reload_doc();
				},
			});
		}).addClass("btn-primary");
	},
});
