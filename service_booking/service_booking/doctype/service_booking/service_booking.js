// Copyright (c) 2026, David Gitau and contributors
// For license information, please see license.txt

frappe.ui.form.on("Service Booking", {
	refresh(frm) {
		if (frm.doc.route) {
			const url = frm.doc.route.startsWith("http") ? frm.doc.route : `/${frm.doc.route}`;
			frm.add_web_link(url, "See on Website", true);
		}
	},
});
