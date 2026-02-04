import frappe
from frappe.utils import nowdate
from frappe import _
import json
import traceback


SERVICE_DETAIL_FIELD_MAPPING = {
    "VIP Chauffeur Service": "rental_details",
    "Self-Drive Rental": "rental_details",
    "Airport Transfer": "airport_transfer",
    "Event Transport": "event_transport",
    "Wedding Transport": "event_transport",
    "Chauffeur Hourly": "rental_details"
}

@frappe.whitelist(allow_guest=True)
def update_booking_details():
    try:
        # 1. Capture Data from Form (Multipart) or JSON
        # If multipart/form-data, data is in frappe.form_dict. Files in frappe.request.files.
        raw_data = frappe.local.form_dict
        
        # If the frontend sent arrays/objects via FormData, they are JSON strings. Parse them.
        data = {}
        for k, v in raw_data.items():
            try:
                data[k] = json.loads(v) if isinstance(v, str) and (v.startswith('[') or v.startswith('{')) else v
            except:
                data[k] = v

        data.pop("cmd", None)

        booking_name = data.get("booking_name")
        service_type = data.get("service_type")

        if not booking_name or not service_type:
            return {"status": "error", "message": "Missing booking_name or service_type"}

        booking_doc = frappe.get_doc("Service Booking", booking_name)
        table_fieldname = SERVICE_DETAIL_FIELD_MAPPING.get(service_type)
        
        if not table_fieldname:
            return {"status": "error", "message": f"No detail table mapped for {service_type}"}

        # Get metadata to identify field types
        meta_field = booking_doc.meta.get_field(table_fieldname)
        child_meta = frappe.get_meta(meta_field.options)
        child_fields = {f.fieldname: f for f in child_meta.fields}

        child_row_data = {}

        # 2. Process Files from Request
        # Any file uploaded via FormFields.FileField will be in frappe.request.files
        if hasattr(frappe.request, 'files'):
            for fieldname, file_obj in frappe.request.files.items():
                # We only save the file if the field exists in the child table
                if fieldname in child_fields:
                    f = frappe.get_doc({
                        "doctype": "File",
                        "file_name": file_obj.filename,
                        "content": file_obj.read(),
                        "attached_to_doctype": "Service Booking",
                        "attached_to_name": booking_name,
                        "is_private": 0
                    })
                    f.insert(ignore_permissions=True)
                    child_row_data[fieldname] = f.file_url

        # 3. Process Text/Data Fields
        for key, value in data.items():
            if key in ["booking_name", "service_type"] or key in child_row_data:
                continue

            field = child_fields.get(key)
            if not field:
                continue

            # Handle existing files (strings) or normal data
            if field.fieldtype in ("Table", "Table MultiSelect"):
                # Ensure child tables are in list format
                child_row_data[key] = value if isinstance(value, list) else []
            else:
                child_row_data[key] = value

        # 4. Update Document
        booking_doc.set(table_fieldname, []) # Clear existing to prevent duplicates
        booking_doc.append(table_fieldname, child_row_data)
        
        booking_doc.save(ignore_permissions=True)
        frappe.db.commit()

        return {
            "status": "success",
            "message": f"Booking {booking_name} updated successfully"
        }

    except Exception:
        frappe.log_error(traceback.format_exc(), "Update Booking Error")
        return {"status": "error", "message": "Internal error. Check logs."}
@frappe.whitelist(allow_guest=True)
def create_booking():
    """
    Create a Service Booking from frontend data (JSON)
    Returns structured JSON with status codes and logs all errors.
    """

    try:
        raw_data = frappe.local.form_dict
        if isinstance(raw_data, str):
            try:
                data = json.loads(raw_data)
            except Exception as e:
                frappe.log_error(message=traceback.format_exc(), title="JSON Parsing Error")
                return frappe._dict({
                    "status": "error",
                    "http_status": 400,
                    "message": f"Invalid JSON: {str(e)}"
                })
        elif isinstance(raw_data, dict):
            data = raw_data
        else:
            frappe.log_error(message=f"Invalid data type: {type(raw_data)}", title="Booking Error")
            return frappe._dict({
                "status": "error",
                "http_status": 400,
                "message": "Data must be a JSON object"
            })

        required = ["name", "email", "phone", "service", "rate", "totalAmount"]
        missing_fields = [f for f in required if not data.get(f)]
        if missing_fields:
            msg = f"Missing required fields: {', '.join(missing_fields)}"
            frappe.log_error(message=msg, title="Booking Validation Error")
            return frappe._dict({
                "status": "error",
                "http_status": 400,
                "message": msg
            })

        customer_name = data.get("name")
        customer_email = data.get("email")
        customer_phone = data.get("phone")

        customer = frappe.db.exists("Customer", {"email_id": customer_email})
        if not customer:
            customer_doc = frappe.get_doc({
                "doctype": "Customer",
                "customer_name": customer_name,
                "customer_type": "Individual",
                "email_id": customer_email,
                "phone": customer_phone
            })
            customer_doc.insert(ignore_permissions=True)
            customer = customer_doc.name

        addons = data.get("addons")
        if not isinstance(addons, list):
            addons = []  

        add_ons_amount = 0
        addons_table = []
        for addon in addons:
            if isinstance(addon, dict):
                amount = addon.get("amount", 0)
                add_ons_amount += amount
                addons_table.append({
                    "addon": addon.get("addon") or addon.get("name"),
                    "amount": amount
                })
            elif isinstance(addon, (int, float)):
                add_ons_amount += addon

        booking_doc = frappe.get_doc({
            "doctype": "Service Booking",
            "service_type": data.get("service"),
            "customer": customer,
            "date": data.get("date") or nowdate(),
            "booking_status": "Draft",
            "rate_card": data.get("rate"),
            "base_amount": data.get("baseAmount", 0),
            "add_ons_amount": add_ons_amount,
            "addons": addons_table,
            "total_amount": data.get("totalAmount"),
            "currency": data.get("currency") or "KES"
        })

        booking_doc.insert(ignore_permissions=True)

        return frappe._dict({
            "status": "success",
            "http_status": 200,
            "booking": booking_doc.name
        })

    except Exception as e:
        # log full traceback
        frappe.log_error(message=traceback.format_exc(), title="Booking Creation Exception")
        return frappe._dict({
            "status": "error",
            "http_status": 500,
            "message": str(e)
        })


@frappe.whitelist(allow_guest=True)
def booking_detail(name):
    """Return a single service booking by name."""
    try:
        booking = frappe.get_doc("Service Booking", name).as_dict()
        rate_card = frappe.get_doc("Service Rate Card", booking.get("rate_card")).as_dict() if booking.get("rate_card") else None
        booking["rate_card"] = rate_card
        return booking
    except frappe.DoesNotExistError:
        frappe.throw(_("Service Booking not found"))


@frappe.whitelist(allow_guest=True)
def submit_booking(name):
    """Submit a service booking by name."""
    try:
        booking = frappe.get_doc("Service Booking", name)
        booking.flags.ignore_permissions = True
        booking.submit()
        return {"status": "success", "message": f"Booking {name} submitted successfully"}
    except frappe.DoesNotExistError:
        frappe.throw(_("Service Booking not found"))
    except Exception as e:
        frappe.log_error(traceback.format_exc(), "Booking Submission Error")
        return {"status": "error", "message": str(e)}
