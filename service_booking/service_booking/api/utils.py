import frappe
from frappe import _
import json
from math import ceil
import traceback


def paginate(doctype, filters=None, page=1, limit=20, order_by="creation desc"):
    """
    Helper function for paginating any Frappe doctype list.
    Returns full documents (as_dict) for each entry.
    """
    filters = filters or {}

    # Ensure numeric values
    try:
        page = int(page)
        limit = int(limit)
    except Exception:
        page, limit = 1, 20

    offset = (page - 1) * limit

    # Total records
    total = frappe.db.count(doctype, filters=filters)

    # Fetch paginated names only
    records = frappe.get_all(
        doctype,
        filters=filters,
        fields=["name"],
        order_by=order_by,
        start=offset,
        page_length=limit,
    )

    # Load full docs via get_doc()
    data = []
    for rec in records:
        try:
            doc = frappe.get_doc(doctype, rec.name).as_dict()
            data.append(doc)
        except frappe.DoesNotExistError:
            continue  # skip missing entries

    total_pages = ceil(total / limit) if total > 0 else 1

    return {
        "data": data,
        "pagination": {
            "total": total,
            "page": page,
            "limit": limit,
            "pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1,
        },
    }



@frappe.whitelist(allow_guest=True)
def get_link_options(doctype, filters=None, page=1, limit=20):
    """Return paginated link options for a given doctype with optional filters."""
    filters = filters or {}

    # Parse JSON values
    for key, value in filters.items():
        if isinstance(value, str):
            try:
                filters[key] = json.loads(value)
            except Exception:
                pass

    return paginate(doctype, filters=filters, page=page, limit=limit)


@frappe.whitelist(allow_guest=True)
def get_multi_select_options(doctype, filters=None, page=1, limit=20):
    """Return paginated multi-select options for a given doctype with optional filters."""
    filters = filters or {}

    # Parse JSON values
    for key, value in filters.items():
        if isinstance(value, str):
            try:
                filters[key] = json.loads(value)
            except Exception:
                pass

    # Get doctype fields and find first mandatory link field
    meta = frappe.get_meta(doctype)
    link_doctype = None
    
    for df in meta.fields:
        if df.fieldtype == "Link" and df.reqd:
            link_doctype = df.options
            break
    
    if not link_doctype:
        return {
            "status": "error",
            "http_status": 400,
            "message": f"No mandatory link field found in {doctype}"
        }

    return paginate(link_doctype, filters=filters, page=page, limit=limit)  



@frappe.whitelist(allow_guest=True)
def get_required_fields(name):
    """
    Returns field meta for the correct child detail doctype
    based on the Service Type.
    """

    try:
        SERVICE_DETAIL_MAP = {
            "VIP Chauffeur Service": "Transport Rental Detail",
            "Self-Drive Rental": "Transport Rental Detail",
            "Airport Transfer": "Airport Transfer Detail",
            "Event Transport": "Event Transport Detail",
            "Wedding Transport": "Event Transport Detail",
            "Chauffeur Hourly": "Transport Rental Detail"
        }

        SERVICE_DETAIL_FIELD_MAPPING = {
            "VIP Chauffeur Service": "rental_details",
            "Self-Drive Rental": "rental_details",
            "Airport Transfer": "airport_transfer",
            "Event Transport": "event_transport",
            "Wedding Transport": "event_transport",
            "Chauffeur Hourly": "rental_details"
        }

        if name not in SERVICE_DETAIL_MAP:
            return {
                "status": "error",
                "http_status": 400,
                "message": f"No detail mapping found for {name}"
            }

        detail_doctype = SERVICE_DETAIL_MAP[name]
        detail_field = SERVICE_DETAIL_FIELD_MAPPING[name]

        meta = frappe.get_meta(detail_doctype)

        SKIP_TYPES = {
            "Tab Break",
            "HTML", "Fold", "Button"
        }

        SKIP_FIELDS = {
            "name", "parent", "parenttype", "parentfield",
            "owner", "creation", "modified", "modified_by",
            "idx", "docstatus"
        }

        fields = []

        for df in meta.fields:
            if df.fieldtype in SKIP_TYPES:
                continue
            if df.fieldname in SKIP_FIELDS:
                continue

            fields.append({
                "fieldname": df.fieldname,
                "label": df.label,
                "fieldtype": df.fieldtype,
                "options": df.options,
                "reqd": df.reqd,
                "default": df.default,
                "read_only": df.read_only,
                "in_list_view": df.in_list_view,
                "length": df.length,
                "precision": getattr(df, "precision", None)
            })

        return {
            "status": "success",
            "http_status": 200,
            "service": name,
            "detail_doctype": detail_doctype,
            "fields": fields,
            "field": detail_field
        }

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "get_required_fields error")
        return {
            "status": "error",
            "http_status": 500,
            "message": str(e)
        }

