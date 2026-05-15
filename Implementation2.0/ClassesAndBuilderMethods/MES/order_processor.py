"""
order_processor.py — Orchestrates the full MES pipeline for one order.

Steps:
  2. Load and merge preset
  3. Upload shells to BaSyx
  4. Build WorkOrder
  5. Select line
  6. Publish WorkOrder via MQTT
"""

import logging

import requests

import order_store
import preset_loader
import shell_uploader
import workorder_builder
import line_selector
import mqtt_client
import basyx_client

log = logging.getLogger(__name__)

WEBSHOP_URL = "http://localhost:3000"


def _cancel_webshop_order(webshop_order_id: str, reason: str | None = None) -> None:
    """Cancel the order in the webshop to release reserved inventory."""
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
            log.info("Webshop order %s cancelled — inventory released", webshop_order_id)
        else:
            log.warning(
                "Webshop cancel for %s returned %s: %s",
                webshop_order_id, resp.status_code, resp.text,
            )
    except Exception as exc:
        log.warning("Could not reach webshop to cancel order %s: %s", webshop_order_id, exc)


async def process_order(mes_payload: dict) -> None:
    """
    Run the full MES pipeline for a single product order (async, runs in background).

    mes_payload structure:
    {
      "orderNumber": "ORD-XXXXXXXX",
      "placedAt": "...",
      "products": [
        {
          "name": "AAU Mobile Phone",
          "configuration": [
            { "slot": "Bottom Cover", "componentTypeId": "...", "category": "...",
              "quantity": 1, "properties": { "material": "PLA", "color": "Black", ... } },
            ...
          ]
        }
      ]
    }
    """
    order_number = mes_payload.get("orderNumber", "ORD-UNKNOWN")
    webshop_order_id = mes_payload.get("orderId")
    products = mes_payload.get("products", [])

    if not products:
        log.warning("MES payload for %s has no products — skipping", order_number)
        return

    # Process first product only for now (one product per order)
    product = products[0]
    product_name = product.get("name", "AAU Mobile Phone")
    configuration = product.get("configuration", [])

    order_store.add_order(order_number, webshop_id=webshop_order_id)
    log.info("Processing order %s — product: %s", order_number, product_name)

    shell_iris: dict[str, str] = {}
    try:
        # Step 2: Load and merge preset
        merged_preset = preset_loader.load_and_merge(product_name, configuration, order_number)

        # Step 3: Upload all shells to BaSyx
        shell_iris, final_iri = shell_uploader.upload_all(merged_preset, order_number)
        order_store.update_shell_iris(order_number, shell_iris)
        log.info("Shells uploaded. Final product IRI: %s", final_iri)

        # Step 4: Build WorkOrder — enrich properties from BaSyx component type shells
        workorder = workorder_builder.build_workorder(
            merged_preset, configuration, shell_iris, order_number,
            basyx_url=basyx_client.BASYX_URL,
        )
        log.info(
            "WorkOrder built: %d ingredients, %d process steps",
            len(workorder.ingredients),
            len(workorder.process_steps),
        )

        # Step 5: Select production line
        try:
            line_id = line_selector.select_line(workorder)
        except ValueError as exc:
            log.error("No matching production line for order %s: %s", order_number, exc)
            order_store.update_status(order_number, "NO_LINE_AVAILABLE", error=str(exc))
            if webshop_order_id:
                _cancel_webshop_order(webshop_order_id, reason=str(exc))
            if shell_iris:
                log.info("Cleaning up %d shells for cancelled order %s", len(shell_iris), order_number)
                shell_uploader.delete_all(shell_iris)
            return
        log.info("Selected line: %s", line_id)

        # Step 6: Publish WorkOrder via MQTT
        mqtt_client.publish_workorder(line_id, workorder)

        # Update order store with selected line
        order_store.update_status(order_number, "PENDING", line_id)
        log.info("Order %s dispatched to line %s", order_number, line_id)

    except Exception as exc:
        log.exception("Pipeline failed for order %s: %s", order_number, exc)
        order_store.update_status(order_number, "FAILED")
        if shell_iris:
            log.info("Cleaning up %d shells after pipeline failure for order %s", len(shell_iris), order_number)
            shell_uploader.delete_all(shell_iris)
