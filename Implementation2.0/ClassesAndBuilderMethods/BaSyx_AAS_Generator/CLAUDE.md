# CLAUDE.md — BaSyx AAS Generator (YAML side)

Full YAML syntax reference: `YAML_FORMAT_GUIDE.txt` (same folder)
React/Next.js configurator docs: `made-react-app/CLAUDE.md`

---

## Keeping this file up to date

When we add or change something non-obvious — a new file type, a new YAML field, a new convention, a change to how the generator consumes templates — update this file before ending the session.

---

## Five file types and what they do

| File type | Folder | Purpose |
|---|---|---|
| Shell template | `shell_templates/*.yaml` | Abstract structural blueprint — declares which submodels a shell type must/may contain. No `shell:` field, no `id:`, no values. Referenced by presets via `shell:` and by type shells via `shell:`. |
| Category type shell | `shell_templates/*.yaml` | Category-level AAS Type definition. Has `kind: "Type"`, its own AAS IRI, `submodel_templates:` (IRI refs), `include:` (which optional collections apply), `submodels:` (static defaults shared by all variants), and `derived:` (patterns for ModelNumber/DisplayName/Description). Referenced by presets via `type:`. Defines its parent blueprint via `shell:`. |
| Submodel template | `submodel_templates/*.yaml` | Defines the field schema for one submodel. Consumed by the configurator UI to render forms. No concrete values here. |
| Shell preset | `shell_presets/*.yaml` | Contains only the configurable/variable delta for one specific variant. Uses `type:` to inherit static values from a category type shell, or `shell:` directly for single-item categories. Consumed by the configurator generator. |
| Shell instance | `shell_templates/` (`kind: Instance`) | A specific physical asset's shell descriptor. Not the same as a preset. |

`shell_templates/` now contains two kinds of YAML:
- **Abstract blueprints** (`component_shell.yaml`, `sub_assembly_shell.yaml`) — no `shell:` field, no `id:`, no `submodels:` values; only declare which submodels are required/optional.
- **Category type shells** (`bottom_cover.yaml`, `top_cover.yaml`, etc.) — have `shell:`, `id:`, `submodel_templates:`, `include:`, `submodels:` with defaults, and `derived:` patterns. Referenced by presets via `type:`.

Key fields on category type shells:
- `submodel_templates:` — IRI refs to submodel templates; designed for future AAS server fetching
- `include:` — which optional collections apply; used by configurator UI; generator ignores it
- `derived:` — token patterns for ModelNumber/DisplayName/Description resolved from MaterialProperties; stripped after resolution
- `submodels:` — static default values shared by all variants in this category

Presets use either `shell:` (old style, direct — for single-item categories) or `type:` (new style — for multi-variant categories). `type:` auto-supplies `shell:`, `include:`, static values, and `derived:` patterns via `resolve_type()` / `resolvePresetType()`.

Do NOT mix formats between types — see `YAML_FORMAT_GUIDE.txt` for the exact structure of each.

---

## How the layers connect

```
shell_template (abstract)  ──references──▶  submodel_templates  (via template_id URI)
        ▲
        │  shell: "component_shell"
category_type_shell  ──static defaults + derived patterns──▶  submodels: { ... }
        ▲
        │  type: "bottom_cover"
shell_preset  ──configurable delta──▶  submodels: { Weight_g, Material, Color, Finish }
```

Resolution: `resolve_type()` (Python) / `resolvePresetType()` (TypeScript) deep-merges the preset delta on top of the type shell's `submodels:`, then resolves `derived:` patterns using `MaterialProperties` values as tokens. Result is identical to an old-style fully-inlined preset.

Presets without `type:` (using `shell:` directly) bypass this resolution entirely — they remain fully inlined.

The link between a shell template and a submodel template is the `template_id` URI. If this URI doesn't match the `id` field in the submodel template file, the configurator will show a warning and render no fields.

---

## IRI scheme

```
Shells:    https://aausmartlab.org/Shells/{Category}/{Type}/{Name}
Submodels: https://aausmartlab.org/Submodels/Templates/{TemplateName}
Semantics: https://aausmartlab.org/Semantics/{FieldName}
```

Examples:
- `https://aausmartlab.org/Shells/Component/Fuse/Fuse_16A_SB`
- `https://aausmartlab.org/Submodels/Templates/BillOfMaterials`

---

## BOM entry granularity rule

`Quantity` on a BOM entry is informational only. If individual components will each need a separate `ComponentInstanceRef` (tracked individually in production), they **must be separate entries** — one per physical item, each with `Quantity: 1`. A single entry with `Quantity: 2` cannot hold two distinct instance refs.

---

## ServiceRequired auto-derivation (final products only)

When `shell_type == "final_product_shell"`, `form_to_aas.py` automatically derives and appends a `ServiceRequired` submodel from the BOP's `ProcessSteps`. Each step with a `ProcessType` field produces one `CapabilityEntry` (`CapabilityType` + `ProcessStepRef`). The `ProcessStepRef` is computed using the same sanitisation logic as the BOP `entry_template: "{Operation}_{N}"`.

Auto-derivation is **skipped** if the caller already passes a `service_required` submodel input with `RequiredCapabilities` entries — manual input takes precedence.

Do not add a `ServiceRequired` section to final product presets; the generator handles it.

---

## BOP capability params (non-obvious)

In a shell preset, a process step can include a `CapabilityParams:` block:

```yaml
ProcessSteps:
  - Operation: "Drilling"
    CapabilityParams:
      DrillingParameters:
        BitDiameter_mm: 5.0
```

At generation time the configurator **strips `CapabilityParams` from the step** and writes it to a separate capability submodel. A `RequiredCapabilityRef` pointer is added to the step in its place. The operation name must match a key in the BOP submodel template's `operations` map, which declares which capability template file to use.

---

## `extensible: true` collections

A collection with `extensible: true` in a submodel template renders an "Add entry" button in the configurator UI. The `entry_template` field on that collection controls the `id_short` naming pattern for each new entry — e.g. `{Description}_{N}` produces `Fuse_1_0`, `Fuse_1_1`, etc.

---

## `derived` fields

A property with a `derived: "{Token}-{OtherToken}"` pattern is auto-computed from other form fields. Tokens are matched against a flat context map of all sibling field values plus `AssetName` and `AssetCategory`. Empty tokens cause their surrounding separator to be dropped cleanly.

---

## Generation pipeline

Preset/form data → `POST /api/aas-configurator/generate` (Next.js) → `form_to_aas.py` (Python) → BaSyx-compatible AAS Environment JSON → uploadable to BaSyx server.

The Python script path must be configured once per machine in the configurator Settings panel.
