/**
 * Type-based inventory and orders schema.
 * Orders specify component types and quantities, not specific instances.
 * Instances are assigned to orders during production fulfillment.
 */

export interface ComponentType {
  id: string;                // Unique type ID, e.g. "bottom_cover_pla_blue_v1"
  category: string;          // e.g. "Bottom Cover"
  material?: string;         // e.g. "PLA"
  color?: string;            // e.g. "Blue"
  finish?: string;           // e.g. "Textured" (covers)
  currentRating?: string;    // e.g. "16A" (fuses, PCB)
  voltageRating?: string;    // e.g. "250V" (fuses, PCB)
  version?: string;          // e.g. "slow-blow" (fuse type)
  aasTypeIri?: string;       // AAS component type shell IRI, e.g. "https://aausmartlab.org/Shells/Component/BottomCover/BottomCover3DP"
  name: string;              // Human-readable name
  description?: string;      // Optional description
  createdAt: string;         // ISO timestamp
}

export interface InventoryItem {
  componentTypeId: string;   // Foreign key to component_types
  quantityAvailable: number;
  quantityReserved: number;
  lastUpdated: string;       // ISO timestamp
}

export interface OrderItem {
  orderItemId: string;       // UUID for this line item
  orderId: string;
  componentTypeId: string;
  quantity: number;
  addedAt: string;           // ISO timestamp
}

export type OrderStatus = "pending" | "in_production" | "fulfilled" | "cancelled";

export interface AasOrder {
  orderId: string;
  placedAt: string;
  cancelledAt: string | null;
  cancellationReason: string | null;
  reserved_session: string | null;
  status: OrderStatus;
  startedAt: string | null;
  fulfilledAt: string | null;
}

export interface PlacedOrder extends AasOrder {
  items: (OrderItem & { component: ComponentType })[];
}

export interface ComponentWithInventory extends ComponentType {
  quantityAvailable: number;
  quantityReserved: number;
}

// SQL schema definitions
export const CREATE_COMPONENT_TYPES_TABLE_SQL = `
  CREATE TABLE IF NOT EXISTS component_types (
    id          TEXT PRIMARY KEY,
    category    TEXT NOT NULL,
    material    TEXT,
    color       TEXT,
    finish      TEXT,
    current_rating TEXT,
    voltage_rating TEXT,
    version     TEXT,
    aas_type_iri TEXT,
    name        TEXT NOT NULL,
    description TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
  )
`;

// Idempotent migrations for existing tables missing the new columns
export const MIGRATE_COMPONENT_TYPES_SQL = [
  `ALTER TABLE component_types ADD COLUMN IF NOT EXISTS finish TEXT`,
  `ALTER TABLE component_types ADD COLUMN IF NOT EXISTS current_rating TEXT`,
  `ALTER TABLE component_types ADD COLUMN IF NOT EXISTS voltage_rating TEXT`,
  `ALTER TABLE component_types ADD COLUMN IF NOT EXISTS aas_type_iri TEXT`,
];

export const MIGRATE_ORDERS_SQL = [
  `ALTER TABLE aas_orders ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'pending'`,
  `ALTER TABLE aas_orders ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ`,
  `ALTER TABLE aas_orders ADD COLUMN IF NOT EXISTS fulfilled_at TIMESTAMPTZ`,
  `ALTER TABLE aas_orders ADD COLUMN IF NOT EXISTS cancellation_reason TEXT`,
];

export const CREATE_INVENTORY_TABLE_SQL = `
  CREATE TABLE IF NOT EXISTS inventory (
    component_type_id    TEXT PRIMARY KEY REFERENCES component_types(id) ON DELETE CASCADE,
    quantity_available   INTEGER NOT NULL DEFAULT 0,
    quantity_reserved    INTEGER NOT NULL DEFAULT 0,
    last_updated         TIMESTAMPTZ NOT NULL DEFAULT NOW()
  )
`;

export const CREATE_ORDERS_TABLE_SQL = `
  CREATE TABLE IF NOT EXISTS aas_orders (
    order_id         TEXT PRIMARY KEY,
    placed_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    cancelled_at     TIMESTAMPTZ,
    reserved_session TEXT,
    status           TEXT NOT NULL DEFAULT 'pending',
    started_at       TIMESTAMPTZ,
    fulfilled_at     TIMESTAMPTZ
  )
`;

export const CREATE_ORDER_ITEMS_TABLE_SQL = `
  CREATE TABLE IF NOT EXISTS order_items (
    order_item_id      TEXT PRIMARY KEY,
    order_id           TEXT NOT NULL REFERENCES aas_orders(order_id) ON DELETE CASCADE,
    component_type_id  TEXT NOT NULL REFERENCES component_types(id),
    quantity           INTEGER NOT NULL,
    added_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(order_id, component_type_id)
  )
`;

// Helper functions
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function rowToComponentType(row: Record<string, any>): ComponentType {
  const createdAt = row.created_at;
  return {
    id: row.id,
    category: row.category ?? "",
    material: row.material ?? undefined,
    color: row.color ?? undefined,
    finish: row.finish ?? undefined,
    currentRating: row.current_rating ?? undefined,
    voltageRating: row.voltage_rating ?? undefined,
    version: row.version ?? undefined,
    aasTypeIri: row.aas_type_iri ?? undefined,
    name: row.name ?? "",
    description: row.description ?? undefined,
    createdAt: createdAt instanceof Date ? createdAt.toISOString() : createdAt,
  };
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function rowToInventoryItem(row: Record<string, any>): InventoryItem {
  const lastUpdated = row.last_updated;
  return {
    componentTypeId: row.component_type_id,
    quantityAvailable: row.quantity_available ?? 0,
    quantityReserved: row.quantity_reserved ?? 0,
    lastUpdated: lastUpdated instanceof Date ? lastUpdated.toISOString() : lastUpdated,
  };
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function rowToOrderItem(row: Record<string, any>): OrderItem {
  const addedAt = row.added_at;
  return {
    orderItemId: row.order_item_id,
    orderId: row.order_id,
    componentTypeId: row.component_type_id,
    quantity: row.quantity ?? 1,
    addedAt: addedAt instanceof Date ? addedAt.toISOString() : addedAt,
  };
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function rowToOrder(row: Record<string, any>): AasOrder {
  const placedAt = row.placed_at;
  const cancelledAt = row.cancelled_at;
  const startedAt = row.started_at;
  const fulfilledAt = row.fulfilled_at;
  return {
    orderId: row.order_id,
    placedAt: placedAt instanceof Date ? placedAt.toISOString() : placedAt,
    cancelledAt: cancelledAt instanceof Date ? cancelledAt.toISOString() : (cancelledAt ?? null),
    cancellationReason: row.cancellation_reason ?? null,
    reserved_session: row.reserved_session ?? null,
    status: (row.status ?? "pending") as OrderStatus,
    startedAt: startedAt instanceof Date ? startedAt.toISOString() : (startedAt ?? null),
    fulfilledAt: fulfilledAt instanceof Date ? fulfilledAt.toISOString() : (fulfilledAt ?? null),
  };
}
