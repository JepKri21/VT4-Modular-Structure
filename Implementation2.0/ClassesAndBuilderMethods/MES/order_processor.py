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

import order_store
import preset_loader
import shell_uploader
import workorder_builder
import line_selector
import mqtt_client
import basyx_client

log = logging.getLogger(__name__)


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
    products = mes_payload.get("products", [])

    if not products:
        log.warning("MES payload for %s has no products — skipping", order_number)
        return

    # Process first product only for now (one product per order)
    product = products[0]
    product_name = product.get("name", "AAU Mobile Phone")
    configuration = product.get("configuration", [])

    order_store.add_order(order_number)
    log.info("Processing order %s — product: %s", order_number, product_name)

    try:
        # Step 2: Load and merge preset
        merged_preset = preset_loader.load_and_merge(product_name, configuration, order_number)

        # Step 3: Upload all shells to BaSyx
        shell_iris, final_iri = shell_uploader.upload_all(merged_preset, order_number)
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
        line_id = line_selector.select_line(workorder)
        log.info("Selected line: %s", line_id)

        # Step 6: Publish WorkOrder via MQTT
        mqtt_client.publish_workorder(line_id, workorder)

        # Update order store with selected line
        order_store.update_status(order_number, "PENDING", line_id)
        log.info("Order %s dispatched to line %s", order_number, line_id)

    except Exception as exc:
        log.exception("Pipeline failed for order %s: %s", order_number, exc)
        order_store.update_status(order_number, "FAILED")
