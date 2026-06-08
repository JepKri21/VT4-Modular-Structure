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
    batch_id = mes_payload.get("orderNumber", "ORD-UNKNOWN")
    webshop_order_id = mes_payload.get("orderId")
    products = mes_payload.get("products", [])

    if not products:
        log.warning("MES payload for %s has no products — skipping", batch_id)
        return

    batch_total = len(products)
    log.info(
        "Processing batch %s — %d product(s)", batch_id, batch_total
    )

    # Each product in the batch becomes its own WorkOrder with order_id
    # "<batch_id>-<n>". They share batch_id so the UI can show "n/N".
    for product in products:
        index = product.get("productIndex") or (products.index(product) + 1)
        order_number = (
            batch_id if batch_total == 1 else f"{batch_id}-{index}"
        )
        await _process_single_product(
            product=product,
            order_number=order_number,
            webshop_order_id=webshop_order_id,
            batch_id=batch_id,
            batch_index=int(index),
            batch_total=batch_total,
        )


async def _process_single_product(
    *,
    product: dict,
    order_number: str,
    webshop_order_id: str | None,
    batch_id: str,
    batch_index: int,
    batch_total: int,
) -> None:
    """Pipeline for one product within a batch. Same logic as the
    pre-batch implementation; just parameterised over (order_number,
    product) and tagged with batch coordinates at enqueue time.
    """
    product_name = product.get("name", "AAU Mobile Phone")
    configuration = product.get("configuration", [])

    order_store.add_order(order_number, webshop_id=webshop_order_id)
    log.info(
        "Processing order %s — product: %s (batch %s/%s)",
        order_number, product_name, batch_index, batch_total,
    )

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

        # Step 6: Enqueue WorkOrder. The dispatcher (running alongside
        # this service) is responsible for actually publishing to MQTT
        # when line capacity is available — see queue_manager / dispatcher.
        # The payload stored on the queue is the same dict the line
        # controller's MES_TOPIC subscriber expects.
        try:
            import queue_manager
            from mqtt_client import _workorder_to_pascal_dict
            payload = _workorder_to_pascal_dict(workorder)
            queue_manager.enqueue(
                order_id=order_number,
                payload=payload,
                line_id=line_id,
                product_ref=workorder.product_reference,
                priority=getattr(workorder, "priority", 100) or 100,
                batch_id=batch_id,
                batch_index=batch_index,
                batch_total=batch_total,
            )
        except Exception as exc:
            log.exception("Failed to enqueue %s: %s", order_number, exc)
            order_store.update_status(order_number, "FAILED")
            if shell_iris:
                shell_uploader.delete_all(shell_iris)
            return

        # Reflect "queued, waiting for capacity" in the legacy store so
        # the existing MES dashboard endpoints keep working.
        order_store.update_status(order_number, "QUEUED", line_id)
        log.info("Order %s queued for line %s", order_number, line_id)

    except Exception as exc:
        log.exception("Pipeline failed for order %s: %s", order_number, exc)
        order_store.update_status(order_number, "FAILED")
        if shell_iris:
            log.info("Cleaning up %d shells after pipeline failure for order %s", len(shell_iris), order_number)
            shell_uploader.delete_all(shell_iris)
