# Copyright (c) 2026, David Gitau and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class ServiceRateCard(Document):
    def autoname(self):
        service = frappe.get_value("Service Type", self.service_type, "service_code")

        if not service:
            frappe.throw("Service Type is missing service code.")

        self.name = frappe.model.naming.make_autoname(f"SRC-{service}-.#####")
