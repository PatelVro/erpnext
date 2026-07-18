// Sales Order form: stage the draft Delivery Note for SELF orders
// (docs/OPERATIONS.md §4). Calls the same whitelisted, SELF-only,
// idempotent service used from the console; submission stays human (INV-8).
frappe.ui.form.on("Sales Order", {
	refresh(frm) {
		if (frm.doc.docstatus !== 1) return;
		if (frm.doc.co_fulfillment_type !== "SELF") return;

		frm.add_custom_button(
			__("Draft Delivery Note (CO)"),
			() => {
				frappe.call({
					method:
						"canadian_outlet.co_inventory.delivery_note_service.create_draft_delivery_note",
					args: { sales_order: frm.doc.name },
					freeze: true,
					callback(r) {
						if (r.message) {
							frappe.set_route("Form", "Delivery Note", r.message);
						}
					},
				});
			},
			__("Create")
		);
	},
});
