import frappe
from frappe import _
import json
from math import ceil
from .utils import paginate

@frappe.whitelist(allow_guest=True)
def groups():
    """Return paginated item groups (full docs)."""
    args = frappe._dict(frappe.request.args)

    args.pop("cmd", None)
    page = int(args.pop("page", 1))
    limit = int(args.pop("limit", 20))

    return paginate("Item Group", filters=args, page=page, limit=limit)


@frappe.whitelist(allow_guest=True)
def group_detail(name):
    """Return a single item group by name."""
    try:
        return frappe.get_doc("Item Group", name).as_dict()
    except frappe.DoesNotExistError:
        frappe.throw(_("Item Group not found"))


@frappe.whitelist(allow_guest=True)
def items(filters=None, page=1, limit=20):
    """Return paginated items with optional filters (full docs)."""
    filters = filters or {}

    # Parse JSON values
    for key, value in filters.items():
        if isinstance(value, str):
            try:
                filters[key] = json.loads(value)
            except Exception:
                pass

    return paginate("Item", filters=filters, page=page, limit=limit)


@frappe.whitelist(allow_guest=True)
def item_detail(name):
    """Return a single item by name or item_code."""
    item_name = frappe.db.get_value(
        "Item", {"name": name}, "name"
    ) or frappe.db.get_value("Item", {"item_code": name}, "name")

    if not item_name:
        frappe.throw(_("Item not found"))

    return frappe.get_doc("Item", item_name).as_dict()


@frappe.whitelist(allow_guest=True)
def services(filters=None, page=1, limit=20):
    """Return paginated services with optional filters (full docs)."""
    filters = filters or {}

    # Parse JSON values
    for key, value in filters.items():
        if isinstance(value, str):
            try:
                filters[key] = json.loads(value)
            except Exception:
                pass

    return paginate("Service Type", filters=filters, page=page, limit=limit)


@frappe.whitelist(allow_guest=True)
def service_detail(name):
    """Return a single service type by name."""
    try:
        service = frappe.get_doc("Service Type", name).as_dict()
        service_rates = service_type_rates(name)
        service["rate_cards"] = service_rates
        return service
    except frappe.DoesNotExistError:
        frappe.throw(_("Service Type not found"))


@frappe.whitelist(allow_guest=True)
def service_type_rates(service_type):
    """Return all service rate cards for a given service type."""
    try:
        rate_cards = frappe.get_all(
            "Service Rate Card", filters={"service_type": service_type}, fields=["name"]
        )

        data = []
        for card in rate_cards:
            try:
                doc = frappe.get_doc("Service Rate Card", card.name).as_dict()
                data.append(doc)
            except frappe.DoesNotExistError:
                continue

        return data
    except Exception:
        frappe.throw(_("Error fetching service rates"))


@frappe.whitelist(allow_guest=True)
def service_rates(filters=None, page=1, limit=20):
    """Return paginated services with optional filters (full docs)."""
    filters = filters or {}

    # Parse JSON values
    for key, value in filters.items():
        if isinstance(value, str):
            try:
                filters[key] = json.loads(value)
            except Exception:
                pass

    return paginate("Service Rate Card", filters=filters, page=page, limit=limit)


@frappe.whitelist(allow_guest=True)
def service_rate_detail(name):
    """Return a single service rate card by name."""
    try:
        return frappe.get_doc("Service Rate Card", name).as_dict()
    except frappe.DoesNotExistError:
        frappe.throw(_("Service Rate Card not found"))
