"""webshop_notify.py — notify the webshop of an order's terminal outcome so it
can release its inventory reservation.

Webshop reservations are per component TYPE (a quantity), not per instance — the
specific instance consumed is only decided at runtime — so the webshop only needs
the order's outcome, never which shells were used.

Kept in its own module so both order_processor (cancel on failure) and
mqtt_client (complete on success) can use it without an import cycle.
"""

import logging

import requests

log = logging.getLogger(__name__)

WEBSHOP_URL = "http://localhost:3000"


def complete_order(webshop_order_id: str) -> bool:
    """Advance a webshop order to 'fulfilled', releasing its reserved inventory.

    The webshop enforces a stepwise state machine (pending -> in_production ->
    fulfilled), so this PATCHes through in_production first. Best-effort and safe
    to call more than once: a PATCH from an already-terminal state is rejected by
    the webshop (HTTP 400) and never double-releases the reservation. Never raises.

    Returns True if at least one transition was accepted.
    """
    advanced = False
    try:
        for status in ("in_production", "fulfilled"):
            resp = requests.patch(
                f"{WEBSHOP_URL}/api/inventory/order",
                json={"orderId": webshop_order_id, "status": status},
                timeout=5,
            )
            if resp.ok:
                advanced = True
            else:
                log.debug(
                    "Webshop PATCH %s -> %s returned %s: %s",
                    webshop_order_id, status, resp.status_code, resp.text[:120],
                )
        if advanced:
            log.info("Webshop order %s fulfilled — inventory reservation released", webshop_order_id)
    except Exception as exc:
        log.warning("Could not reach webshop to complete order %s: %s", webshop_order_id, exc)
    return advanced


def cancel_order(webshop_order_id: str, reason: str | None = None) -> bool:
    """Cancel a webshop order, releasing its still-reserved inventory.

    Called when an order aborts on the production line. The webshop DELETE marks
    the order cancelled, which drops it out of the open-order set the reservation
    count is derived from — so the parts that were never consumed return to
    availability. Parts already assembled into completed sub-assemblies stay
    consumed: their instance shells remain referenced in those BOMs and the sync
    keeps excluding them. Best-effort, idempotent (a repeat cancel is rejected),
    never raises.

    Returns True if the cancel was accepted.
    """
    try:
        params: dict = {"orderId": webshop_order_id}
        if reason:
            params["reason"] = reason
        resp = requests.delete(
            f"{WEBSHOP_URL}/api/inventory/order",
            params=params,
            timeout=5,
        )
        if resp.ok:
            log.info("Webshop order %s cancelled — reservation released", webshop_order_id)
            return True
        log.debug(
            "Webshop cancel %s returned %s: %s",
            webshop_order_id, resp.status_code, resp.text[:120],
        )
    except Exception as exc:
        log.warning("Could not reach webshop to cancel order %s: %s", webshop_order_id, exc)
    return False
