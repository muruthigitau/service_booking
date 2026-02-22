# Copyright (c) 2026, David Gitau and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class ServiceBookingPayment(Document):
    def autoname(self):
        self.name = frappe.model.naming.make_autoname(f"{self.service_booking}-.##")

    def on_payment_authorized(self, payment_status: str):
        if payment_status in ("Authorized", "Completed"):
            self.paid = 1
            self.save()
            booking = frappe.get_doc("Service Booking", self.service_booking)
            booking.flags.ignore_permissions = True
            booking.update_payments()
