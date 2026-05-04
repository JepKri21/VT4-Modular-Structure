# Made React App - AAS Configurator Documentation

**Last Updated**: May 1, 2026

## Overview

The made-react-app uses the **AAS Configurator** (Asset Administration Shell configurator) for industrial asset configuration. This is a form-based configurator that allows users to fill out complex nested forms for industrial asset definition.

---

## AAS Configurator

### Location
- Page: `/app/aas-configurator/page.tsx`
- Components: `/components/aas-configurator/`

### Purpose
Form-based configurator for Asset Administration Shell (AAS) configuration. Allows users to fill out complex nested forms for industrial asset definition with support for shell types, presets, submodel templates, and derived fields.

### Key Components

#### Main Components
- **Page** (`/app/aas-configurator/page.tsx`) - Main page orchestrating the configurator form
- **FieldRenderer** (`/components/aas-configurator/FieldRenderer.tsx`) - Renders form fields based on template structure

#### Type Definitions
- **types.ts** (`/components/aas-configurator/types.ts`) - Comprehensive TypeScript types and utility functions

### Key Features
- **Template-Based Forms**: Forms generated dynamically from shell templates and submodel templates
- **Dynamic Field Rendering**: Supports multiple field types (properties, collections, lists, references, ranges, multi-language)
- **Derived Fields**: Automatic field computation using patterns like `"{name}-{category}"`
- **Capability Management**: Inline rendering of operation capabilities, including `CapabilityCategory` selection for offered vs required capability submodels
- **BOM & Process Steps**: Reference pickers for components and process steps
- **Validation**: Min/max constraints on numeric fields, required field validation
- **Import/Export**: Load presets and export configurations to JSON

### Supported Field Types

#### Primitive Types
- `xs:string` - Text input
- `xs:integer` - Integer input with optional min/max validation
- `xs:float`, `xs:double` - Number inputs with optional min/max validation
- `xs:boolean` - Checkbox toggle

#### Special Property Rendering
- `CapabilityCategory` - Select input with `Offered` and `Required` values

#### Complex Types
- **property** - Single value property
- **collection** - Non-extensible nested object with fixed structure
- **list** - Extensible array that can grow/shrink with add/remove buttons
- **multi_language_property** - Language-specific text entries (e.g., English, German)
- **reference_element** - References to other elements or BOM entries
- **range** - Range specification with min/max values

### Data Types

```typescript
interface TemplateElement {
  type: "property" | "collection" | "list" | "reference_element" | 
        "multi_language_property" | "range";
  id_short: string;
  semantic_id?: string;
  description?: string;
  value_type?: string;
  cardinality?: string;
  extensible?: boolean;      // For lists that can grow
  entry_template?: string;   // Template for new list entries
  elements?: TemplateElement[]; // For nested structures
  qualifiers?: Qualifier[];  // Constraints (range_min, range_max, etc.)
  options?: string[];        // For dropdown selections
  ref_source?: string;       // "process_steps" for step references
  derived?: string;          // Pattern for auto-computed values
}

interface FormData {
  [key: string]: FormValue | FormData[] | FormData;
}

interface FormValue {
  // Primitive or complex value type
}

interface OperationCapability {
  id_short: string;
  template_file: string;
  template_id: string;
}

interface ShellPreset {
  id_short: string;
  name: string;
  description?: string;
  data: FormData;
}
```

### Key Utility Functions

#### Form Data Manipulation
- **`flattenFormData(data, out?)`** - Converts nested FormData into a single-level `{ id_short: stringValue }` map for context resolution
- **`resolveDerived(pattern, context)`** - Resolves pattern tokens (e.g., `"{name}-{category}"`) using context values, dropping empty segments
- **`applyDerivedFields(elements, formData, context)`** - Auto-fills derived fields in form using context
- **`mergePresetIntoForm(preset, elements, formData)`** - Merges shell preset data into form state
- **`applyPattern(pattern, name, category)`** - Applies simple naming patterns to generated fields
- **`computeBomEntryIdShort(entry)`** - Generates standardized BOM entry identifiers
- **`computeStepIdShort(step)`** - Generates standardized process step identifiers

#### Helper Functions
- **`isOptional(element)`** - Checks if element is optional based on cardinality
- **`labelFor(id_short)`** - Converts id_short to readable label (replaces underscores with spaces)

### Component Workflow

```
1. Load Shell Presets & Submodel Templates
   ↓
2. Initialize Form State with template structure
   ↓
3. FieldRenderer recursively creates form fields:
   - Properties → input fields
   - Collections → nested sections
   - Lists → arrays with add/remove buttons
   - References → dropdown pickers
   ↓
4. User fills out form (nested structures supported)
   ↓
5. Derived fields auto-populate:
   - resolveDerived() resolves patterns
   - applyDerivedFields() fills empty fields
   ↓
6. Capabilities added/edited inline
   ↓
7. BOM entries and process steps referenced
   ↓
8. Configuration exported to JSON or downloaded
```

### State Management
- React `useState` for form data, UI state, and control states
- Context-aware field calculations for derived values
- Validation state tracked during form submission

### Component Hierarchy

```
made-react-app/
└── components/
    └── aas-configurator/
        ├── FieldRenderer.tsx         (Form field renderer)
        └── types.ts                  (Type definitions & utilities)

    app/
    └── aas-configurator/
        └── page.tsx                  (AAS Configurator Page)
```

### Legacy Components (Not in Use)
- `/app/configurator/` - Product Configurator (legacy)

---

## API Integration

### AAS Configurator Endpoints
- **GET** `/api/aas-configurator/config` - Load the configured BaSyx generator path
- **POST** `/api/aas-configurator/config` - Save the BaSyx generator path
- **GET** `/api/aas-configurator/shell-types` - Load available shell types and their submodel slots
- **GET** `/api/aas-configurator/presets?shell={shell}` - Load shell presets, optionally filtered by shell type
- **GET** `/api/aas-configurator/presets/{name}` - Load a specific preset by filename
- **GET** `/api/aas-configurator/templates/{name}` - Load a specific submodel template by filename
- **POST** `/api/aas-configurator/generate` - Generate the AAS payload from the configured form data
- **POST** `/api/aas-configurator/upload` - Upload the generated shell and submodels to an AAS server

---

## Key Technologies & Patterns

### State Management
- React `useState` for local form state
- Derived/computed values using utility functions
- Redux available (via `redux.tsx`) if needed for global state

### Type Safety
- TypeScript for all components and utilities
- Extensive interface definitions for AAS form data
- Template-based type generation from API responses

### Rendering Patterns
- Template-based recursive form generation
- Conditional field rendering based on `value_type` and `type`
- Special-case rendering for capability category selection
- Support for dynamic arrays and nested collections

### Performance Considerations
- `useMemo` for expensive template transformations
- `useCallback` for event handlers (onChange, onAdd, onRemove)
- Lazy loading of templates and presets
- Efficient context resolution for derived fields

---

## Development Notes

### When Modifying the AAS Configurator

1. **Adding New Field Types**: 
   - Extend `TemplateElement.type` union in `types.ts`
   - Add corresponding renderer case in `FieldRenderer.tsx`
   - Update validation logic if needed

2. **Modifying Form Data Structure**:
   - Update `FormData` and related interfaces in `types.ts`
   - Test nested structure serialization/deserialization

3. **Adding New Capability Metadata**:
   - Add the field to `FieldRenderer.tsx` if it needs special UI handling
   - Make sure the template YAML uses a stable `semantic_id` when the field is meant to be matched across templates
   - Update presets so offered and required capability forms stay aligned

4. **Adding New Utility Functions**:
   - Add to `types.ts` with clear documentation
   - Include type signatures for TypeScript support
   - Test with deeply nested structures

5. **Enhancing Field Validation**:
   - Add qualifier types in `TemplateElement.qualifiers`
   - Update validation in `FieldRenderer.tsx`
   - Test boundary cases (min/max, required fields, etc.)

### Testing Considerations
- Test nested form structures with multiple levels of depth
- Verify derived field calculations work correctly with various context patterns
- Test API error handling for template/preset loading failures
- Validate complex reference pickers (BOM entries, process steps)
- Test export/download functionality with various data types
- Verify form state persistence across component rerenders
- Test edge cases: empty strings, null values, special characters in patterns

### Future Enhancement Areas
- [ ] Add real-time validation feedback during form filling
- [ ] Implement field-level error messages
- [ ] Add template preview/help documentation
- [ ] Implement form state persistence to localStorage
- [ ] Add undo/redo for form changes
- [ ] Support for custom field renderers plugin system
- [ ] Add collaborative editing features
- [ ] Improve performance for large nested forms
- [ ] Add advanced validation rules (cross-field dependencies, conditional requirements)

---

## References

### Related Files
- `aas-config.json` - Global AAS configuration
- `components.json` - Component configuration
- Backend: `Implementation2.0/ProductAndResourceImplementations/`

### BaSyx AAS Generator

The repository includes a small BaSyx-based generator used to produce AAS Submodel
Templates, Submodel Instances, Shell Presets and final JSON suitable for upload to a
BaSyx AAS server. See the detailed YAML guide at
`Implementation2.0/ClassesAndBuilderMethods/BaSyx_AAS_Generator/YAML_FORMAT_GUIDE.txt`.

Location:
- `Implementation2.0/ClassesAndBuilderMethods/BaSyx_AAS_Generator/`

Key files:
- `builders.py` — helpers that convert plain dict configs into BaSyx model objects and
   serialise them. Uses `basyx-python-sdk` and exposes `XS_TYPE_MAP` and helpers.
- `template_generator_class.py` — `AASTemplateBuilder` for creating AAS Submodel
   Templates (ModellingKind.TEMPLATE).
- `instance_generator_class.py` — `AASInstanceBuilder` for creating AAS Submodel
   Instances (ModellingKind.INSTANCE).
- `yaml_to_instance.py` — script to load YAML instance definitions and output or
   upload BaSyx JSON (example usage in YAML guide).
- `yaml_to_template.py`, `yaml_to_shell.py` — helper scripts (use templates/presets).
- `submodel_templates/`, `shell_templates/`, `shell_presets/` — YAML sources used by
   the generator (see YAML format guide for each folder's schema).

Generation flow (high-level):
1. Author a Submodel Template in `submodel_templates/*.yaml` (schema-only).
2. Optionally author Shell Presets in `shell_presets/*.yaml` which map to one or
    more submodels and provide concrete values.
3. Use the template and/or preset scripts to generate BaSyx JSON templates/instances
    via the builder classes. The typical commands are shown in the YAML guide, e.g.: 

```powershell
python yaml_to_template.py submodel_templates/my_submodel.yaml --output out.json
python yaml_to_instance.py Instance_Examples/…/instance.yaml --output out.json
python yaml_to_instance.py Instance_Examples/…/instance.yaml --upload http://localhost:8081
```

Dependencies:
- See `Implementation2.0/ClassesAndBuilderMethods/BaSyx_AAS_Generator/requirements.txt`.
- Main dependency: `basyx-python-sdk` (plus `pyyaml`, `requests`).

Notes:
- `builders.py` creates modelling-kind TEMPLATE submodels for type-level definitions.
- Instance scripts (`yaml_to_instance.py`) use `AASInstanceBuilder` to create
   instance-level JSON suitable for upload.
- The YAML guide contains concrete schema rules and examples — follow it closely
   when authoring templates, instances, or presets.

### Configuration Files
- `app/api/aas-configurator/` - API endpoints for configurator
- `app/aas-configurator/page.tsx` - Main page implementation

### Documentation Files
- `Implementation2.0/Line_Controller/CLAUDE.md` - Line controller documentation
- `Implementation2.0/ClassesAndBuilderMethods/BaSyx_AAS_Generator/YAML_FORMAT_GUIDE.txt` - YAML format guide

---

## Progress Tracking

Use this section to track major updates and changes:

### Completed Features
- [x] Basic form field rendering for primitives
- [x] Nested collection support
- [x] Extensible list management
- [x] Multi-language property support
- [x] Derived field auto-population
- [x] Reference element support
- [x] BOM entry picking
- [x] Process step references
- [x] Export to JSON functionality

### In Progress
- [ ] (Track ongoing work here)

### Planned Features
- [ ] (Track planned features here)

---

**Note**: This documentation should be updated as the AAS Configurator is modified or enhanced. Include significant changes, new features, bug fixes, and architectural updates in the Progress Tracking section above.
