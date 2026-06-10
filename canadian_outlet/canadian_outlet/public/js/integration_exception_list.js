// Integration Exception list: status at a glance (docs/DATA-MODEL.md §5).
frappe.listview_settings["Integration Exception"] = {
	get_indicator(doc) {
		const colors = {
			"Open": "red",
			"In Review": "orange",
			"Resolved": "blue",
			"Ignored": "gray",
			"Failed Replay": "purple",
		};
		return [__(doc.status), colors[doc.status] || "gray", "status,=," + doc.status];
	},
};
