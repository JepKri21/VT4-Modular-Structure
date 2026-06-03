// Mirrors orchestration_snapshot.build_snapshot() in the Line Controller.
// Keep these in sync with that Python module.

export type LineLane = {
  resource_iri: string;
  resource_id: string;
  actor_name: string;
  packml_state: string;
  owner_order: string | null;
  cargo: string | null;
  stuck: boolean;
};

export type OrderStep = {
  step_id: string;
  name: string;
  ingredient: string;
  capability: string;
  precedence: number;
  state: string;
  assigned_resource: string | null;
};

export type LineOrder = {
  order_id: string;
  product_reference: string | null;
  priority: number | null;
  issued_at: string | null;
  current_step: string | null;
  steps: OrderStep[];
};

export type Reservation = {
  instance_iri: string;
  owner_order: string | null;
};

export type OrchestrationSnapshot = {
  schema_version: string;
  timestamp: string;
  orders: LineOrder[];
  lanes: LineLane[];
  reservations: Reservation[];
};

export const SNAPSHOT_TOPIC = "AAUSmartLab/ProductionLine1/Orchestration/Snapshot";
