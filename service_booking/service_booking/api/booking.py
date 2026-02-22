import frappe
from frappe.utils import nowdate
from frappe import _
import json
import traceback

from payments.utils import get_payment_gateway_controller

SERVICE_DETAIL_FIELD_MAPPING = {
    "VIP Chauffeur Service": "rental_details",
    "Self-Drive Rental": "rental_details",
    "Airport Transfer": "airport_transfer",
    "Event Transport": "event_transport",
    "Wedding Transport": "event_transport",
    "Chauffeur Hourly": "rental_details",
}


# ---------------------------
# Utility: Safe Value Normalize
# ---------------------------
def normalize_value(field, value):
    """
    Prevent dict/list from crashing MariaDB.
    Convert to JSON string unless field is Table-type.
    """
    if isinstance(value, dict):
        return json.dumps(value)

    if isinstance(value, list):
        if field.fieldtype in ("Table", "Table MultiSelect"):
            return value
        return json.dumps(value)

    return value


# ---------------------------
# UPDATE BOOKING DETAILS
# ---------------------------
@frappe.whitelist(allow_guest=True)
def update_booking_details():
    try:
        raw_data = frappe.local.form_dict

        # Parse JSON safely
        data = {}
        for k, v in raw_data.items():
            try:
                data[k] = (
                    json.loads(v)
                    if isinstance(v, str) and (v.startswith("{") or v.startswith("["))
                    else v
                )
            except Exception:
                data[k] = v

        data.pop("cmd", None)

        booking_name = data.get("booking_name")
        service_type = data.get("service_type")

        if not booking_name or not service_type:
            return {
                "status": "error",
                "message": "Missing booking_name or service_type",
            }

        booking_doc = frappe.get_doc("Service Booking", booking_name)
        table_fieldname = SERVICE_DETAIL_FIELD_MAPPING.get(service_type)

        if not table_fieldname:
            return {
                "status": "error",
                "message": f"No detail table mapped for {service_type}",
            }

        meta_field = booking_doc.meta.get_field(table_fieldname)
        child_meta = frappe.get_meta(meta_field.options)
        child_fields = {f.fieldname: f for f in child_meta.fields}

        child_row_data = {}

        # -------------------
        # Handle File Uploads
        # -------------------
        if hasattr(frappe.request, "files"):
            for fieldname, file_obj in frappe.request.files.items():
                if fieldname in child_fields:
                    f = frappe.get_doc(
                        {
                            "doctype": "File",
                            "file_name": file_obj.filename,
                            "content": file_obj.read(),
                            "attached_to_doctype": "Service Booking",
                            "attached_to_name": booking_name,
                            "is_private": 0,
                        }
                    )
                    f.insert(ignore_permissions=True)
                    child_row_data[fieldname] = f.file_url

        # -------------------
        # Handle Data Fields
        # -------------------
        for key, value in data.items():
            if key in ["booking_name", "service_type"] or key in child_row_data:
                continue

            field = child_fields.get(key)
            if not field:
                continue

            child_row_data[key] = normalize_value(field, value)

        # Clear and update child table
        booking_doc.set(table_fieldname, [])
        if child_row_data:
            booking_doc.append(table_fieldname, child_row_data)

        booking_doc.save(ignore_permissions=True)
        frappe.db.commit()

        return {
            "status": "success",
            "message": f"Booking {booking_name} updated successfully",
        }

    except Exception:
        frappe.log_error(traceback.format_exc(), "Update Booking Error")
        return {"status": "error", "message": "Internal error. Check logs."}


# ---------------------------
# CREATE OR UPDATE BOOKING
# ---------------------------
@frappe.whitelist(allow_guest=True)
def create_booking():
    try:
        raw_data = frappe.local.form_dict

        data = {}
        for k, v in raw_data.items():
            try:
                data[k] = (
                    json.loads(v)
                    if isinstance(v, str) and (v.startswith("{") or v.startswith("["))
                    else v
                )
            except Exception:
                data[k] = v

        data.pop("cmd", None)

        required = ["name", "email", "phone", "service", "totalAmount"]
        missing_fields = [f for f in required if not data.get(f)]
        if missing_fields:
            return {
                "status": "error",
                "message": f"Missing fields: {', '.join(missing_fields)}",
            }

        service_type = data.get("service")

        # -------------------
        # Customer Handling
        # -------------------
        customer_email = data.get("email")
        customer = frappe.db.exists("Customer", {"email_id": customer_email})

        if not customer:
            customer_doc = frappe.get_doc(
                {
                    "doctype": "Customer",
                    "customer_name": data.get("name"),
                    "customer_type": "Individual",
                    "email_id": customer_email,
                    "phone": data.get("phone"),
                }
            )
            customer_doc.insert(ignore_permissions=True)
            customer = customer_doc.name

        # -------------------
        # Addons
        # -------------------
        addons = data.get("addons") or []
        addons_table = []
        add_ons_total = 0

        rate = data.get("rate_card")
        rate_card = frappe.get_doc("Service Rate Card", rate) if rate else None

        for a in addons:
            addon = (
                next(
                    (item for item in (rate_card.addons or []) if item.addon == a),
                    None,
                )
                if rate_card
                else None
            )
            amt = float(addon.get("amount") or 0)
            add_ons_total += amt
            addons_table.append({"addon": addon.get("addon"), "amount": amt})

        # -------------------
        # Check Existing Draft Booking
        # -------------------
        existing_booking = frappe.db.exists(
            "Service Booking",
            {
                "customer": customer,
                "service_type": service_type,
                "booking_status": "Draft",
            },
        )

        if existing_booking:
            booking_doc = frappe.get_doc("Service Booking", existing_booking)
        else:
            booking_doc = frappe.new_doc("Service Booking")
            booking_doc.service_type = service_type
            booking_doc.customer = customer
            booking_doc.booking_status = "Draft"

        # Update Core Fields
        booking_doc.date = data.get("date") or nowdate()
        booking_doc.rate_card = rate
        booking_doc.vehicle_class = data.get("vehicleClass") or None
        booking_doc.airport = data.get("airport") or None
        booking_doc.base_amount = float(data.get("baseAmount") or 0)
        booking_doc.add_ons_amount = add_ons_total
        booking_doc.total_amount = float(data.get("totalAmount") or 0)
        booking_doc.currency = data.get("currency") or "KES"
        booking_doc.set("addons", addons_table)

        # -------------------
        # Dynamic Child Table
        # -------------------
        table_fieldname = SERVICE_DETAIL_FIELD_MAPPING.get(service_type)

        if table_fieldname:
            meta_field = booking_doc.meta.get_field(table_fieldname)
            child_meta = frappe.get_meta(meta_field.options)
            child_fields = {f.fieldname: f for f in child_meta.fields}

            child_row_data = {}

            for key, value in data.items():
                if key in required or key in [
                    "rate",
                    "baseAmount",
                    "addons",
                    "date",
                ]:
                    continue

                field = child_fields.get(key)
                if not field:
                    continue

                child_row_data[key] = normalize_value(field, value)

            booking_doc.set(table_fieldname, [])
            if child_row_data:
                booking_doc.append(table_fieldname, child_row_data)

        # -------------------
        booking_doc.insert(ignore_permissions=True)

        frappe.db.commit()

        return {
            "status": "success",
            "booking": booking_doc.name,
            "message": _("Booking Saved Successfully"),
        }

    except Exception as e:
        frappe.log_error(traceback.format_exc(), "Create Booking Error")
        return {"status": "error", "message": str(e)}


# ---------------------------
# GET BOOKING DETAIL
# ---------------------------
@frappe.whitelist(allow_guest=True)
def booking_detail(name):
    try:
        booking = frappe.get_doc("Service Booking", name).as_dict()

        if booking.get("rate_card"):
            rate_card = frappe.get_doc(
                "Service Rate Card", booking.get("rate_card")
            ).as_dict()
            booking["rate_card"] = rate_card

        return booking

    except frappe.DoesNotExistError:
        frappe.throw(_("Service Booking not found"))


# ---------------------------
# SUBMIT BOOKING
# ---------------------------
@frappe.whitelist(allow_guest=True)
def submit_booking(name):
    try:
        booking = frappe.get_doc("Service Booking", name)
        booking.flags.ignore_permissions = True
        booking.submit()

        return {
            "status": "success",
            "message": f"Booking {name} submitted successfully",
        }

    except frappe.DoesNotExistError:
        frappe.throw(_("Service Booking not found"))

    except Exception as e:
        frappe.log_error(traceback.format_exc(), "Booking Submission Error")
        return {"status": "error", "message": str(e)}


@frappe.whitelist(allow_guest=True)
def generate_payment_link(booking_id, payment_gateway="PayPal", redirect_to="/"):
    try:
        booking_doc = frappe.get_doc("Service Booking", booking_id)
        booking_doc.flags.ignore_permissions = True
        customer_email = frappe.get_cached_value(
            "Customer", booking_doc.customer, "email_id"
        )

        customer_name = frappe.get_cached_value(
            "Customer", booking_doc.customer, "customer_name"
        )

        route = booking_doc.route

        link = get_payment_link(
            booking_id,
            booking_doc.total_amount,
            booking_doc.currency,
            payment_gateway,
            redirect_to=route or redirect_to,
            email=customer_email,
            name=customer_name,
            title=f"Payment for Service Booking {booking_id}",
        )

        return {"payment_url": link}

    except frappe.DoesNotExistError:
        frappe.throw(_("Service Booking not found"))

    except Exception as e:
        frappe.log_error(traceback.format_exc(), "Generate Payment Link Error")
        return {"status": "error", "message": str(e)}


def get_payment_link(
    reference_docname: str,
    amount: float,
    currency: str,
    payment_gateway: str,
    redirect_to: str = "/",
    email: str | None = None,
    name: str | None = None,
    title: str | None = None,
) -> str:
    payment = record_payment(reference_docname, amount, currency, payment_gateway)
    controller = get_controller(payment_gateway)
    user_full_name = frappe.get_cached_value("User", frappe.session.user, "full_name")

    payment_details = {
        "amount": amount,
        "title": title or f"Payment for Service Booking: {reference_docname}",
        "description": f"{name or user_full_name}'s payment for Service Booking (#{reference_docname})",
        "reference_doctype": "Service Booking Payment",
        "reference_docname": payment.name,
        "payer_email": email or frappe.session.user,
        "payer_name": name or user_full_name,
        "currency": currency,
        "payment_gateway": payment_gateway,
        "redirect_to": redirect_to,
        "payment": payment.name,
    }
    if payment_gateway == "Razorpay" or payment_gateway == "Paymob":
        order = controller.create_order(**payment_details)
        payment_details.update({"order_id": order.get("id")})

    url = controller.get_payment_url(**payment_details)

    return url


def record_payment(
    reference_docname: str,
    amount: float,
    currency: str,
    payment_gateway: str | None = None,
):
    payment_doc = frappe.new_doc("Service Booking Payment")
    payment_doc.flags.ignore_permissions = True
    payment_doc.update(
        {
            "amount": amount,
            "currency": currency,
            "service_booking": reference_docname,
            "payment_gateway": payment_gateway,
        }
    )
    payment_doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return payment_doc


def get_controller(payment_gateway):
    return get_payment_gateway_controller(payment_gateway)
