# Copyright (c) 2026, David Gitau and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
import random


class ServiceBooking(Document):
    def autoname(self):
        service = frappe.get_value("Service Type", self.service_type, "service_code")

        if not service:
            frappe.throw("Service Type is missing service code.")

        random_digits = random.randint(0, 999)
        self.name = frappe.model.naming.make_autoname(
            f"SB-{service}-.YY.-.{random_digits:04d}.#"
        )

    def validate(self):
        if not self.route:
            settings = frappe.get_doc("Service Booking Settings")
            web_url = settings.website_link or ""
            self.route = f"{web_url}/book/{self.name}"

    @frappe.whitelist()
    def update_payments(self):
        payments = frappe.get_all(
            "Service Booking Payment",
            filters={"service_booking": self.name, "paid": 1},
            fields=["amount"],
        )
        total_paid = sum(payment.amount for payment in payments)
        if total_paid >= self.total_amount:
            self.paid = 1
        self.save(ignore_permissions=True)
