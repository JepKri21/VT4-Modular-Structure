"use client";

import React, { useRef, useState } from "react";
import {
  BomEntry,
  FormData,
  FormValue,
  LangEntry,
  ProcessStepEntry,
  TemplateElement,
  isOptional,
  resolveDerived,
} from "./types";
import { ChevronDown, ChevronRight, Plus, Trash2, Wand2 } from "lucide-react";

/* ──────────────────────────────────────────────────────────── helpers ── */

function labelFor(id_short: string) {
  return id_short.replace(/_/g, " ");
}

function inputClass(hasError = false) {
  return `w-full rounded-md border ${hasError ? "border-red-500" : "border-border"} bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary`;
}

/* ──────────────────────────────────────────────────────────── types ── */

interface FieldProps {
  element: TemplateElement;
  value: FormValue | FormData[];
  onChange: (v: FormValue | FormData[]) => void;
  /** prefix for unique ids */
  path: string;
  /** flat key→value map used to resolve {Token} in element.derived patterns */
  context?: Record<string, string>;
  /** operation name → capability template elements; enables inline capability rendering in extensible ProcessStep collections */
  inlineCapabilityMap?: Record<string, TemplateElement[]>;
  /** available BOM entries for RequiredComponents reference pickers */
  bomEntries?: BomEntry[];
  /** available process steps for PredecessorStep pickers */
  processStepEntries?: ProcessStepEntry[];
}

/* ──────────────────────────────── property ── */

function PropertyField({ element, value, onChange, path, context }: FieldProps) {
  const vt = element.value_type ?? "xs:string";
  const id = `${path}-${element.id_short}`;
  const val = (value ?? "") as string | number | boolean;
  const derivedValue =
    element.derived && context ? resolveDerived(element.derived, context) : undefined;

  if (vt === "xs:boolean") {
    return (
      <label className="flex items-center gap-2 cursor-pointer">
        <input
          id={id}
          type="checkbox"
          className="w-4 h-4 accent-primary"
          checked={!!val}
          onChange={(e) => onChange(e.target.checked)}
        />
        <span className="text-sm">{labelFor(element.id_short)}</span>
        {element.description && (
          <span className="text-xs text-muted-foreground ml-1">
            — {element.description}
          </span>
        )}
      </label>
    );
  }

  if (vt === "xs:integer" || vt === "xs:float" || vt === "xs:double") {
    const qualifier = element.qualifiers ?? [];
    const min = qualifier.find((q) => q.type === "range_min")?.value as
      | number
      | undefined;
    const max = qualifier.find((q) => q.type === "range_max")?.value as
      | number
      | undefined;
    return (
      <div className="flex flex-col gap-1">
        <label htmlFor={id} className="text-sm font-medium">
          {labelFor(element.id_short)}
          {element.description && (
            <span className="text-xs text-muted-foreground ml-1">
              — {element.description}
            </span>
          )}
        </label>
        <input
          id={id}
          type="number"
          step={vt === "xs:integer" ? 1 : "any"}
          min={min}
          max={max}
          className={inputClass()}
          value={val === null || val === undefined ? "" : String(val)}
          onChange={(e) =>
            onChange(
              e.target.value === ""
                ? null
                : vt === "xs:integer"
                  ? parseInt(e.target.value, 10)
                  : parseFloat(e.target.value)
            )
          }
        />
      </div>
    );
  }

  if (vt === "xs:duration") {
    return (
      <div className="flex flex-col gap-1">
        <label htmlFor={id} className="text-sm font-medium">
          {labelFor(element.id_short)}
          {element.description && (
            <span className="text-xs text-muted-foreground ml-1">
              — {element.description}
            </span>
          )}
        </label>
        <input
          id={id}
          type="text"
          placeholder="e.g. PT1H30M"
          className={inputClass()}
          value={String(val ?? "")}
          onChange={(e) => onChange(e.target.value)}
        />
      </div>
    );
  }

  // Special rendering for CapabilityCategory properties
  if (
    element.id_short === "CapabilityCategory" ||
    element.semantic_id === "https://aausmartlab.org/Semantics/CapabilityCategory"
  ) {
    const options = ["Offered", "Required"];
    return (
      <div className="flex flex-col gap-1">
        <label htmlFor={id} className="text-sm font-medium">
          {labelFor(element.id_short)}
          {element.description && (
            <span className="text-xs text-muted-foreground ml-1">— {element.description}</span>
          )}
        </label>
        <select
          id={id}
          className={inputClass()}
          value={String(val ?? "")}
          onChange={(e) => onChange(e.target.value || null)}
        >
          <option value="">— select —</option>
          {options.map((o) => (
            <option key={o} value={o}>{o}</option>
          ))}
        </select>
      </div>
    );
  }

  // Default: xs:string / xs:anyURI / etc.
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-sm font-medium flex items-center gap-1.5 flex-wrap">
        {labelFor(element.id_short)}
        {derivedValue && (
          <span className="inline-flex items-center gap-1 text-[10px] text-primary bg-primary/10 rounded px-1.5 py-0.5 font-normal">
            <Wand2 className="w-2.5 h-2.5" /> auto
          </span>
        )}
        {element.description && (
          <span className="text-xs text-muted-foreground font-normal">
            — {element.description}
          </span>
        )}
      </label>
      <input
        id={id}
        type="text"
        className={inputClass()}
        placeholder={derivedValue}
        value={String(val ?? "")}
        onChange={(e) => onChange(e.target.value)}
      />
      {derivedValue && !val && (
        <span className="text-[11px] text-muted-foreground">
          Will use: <span className="font-mono text-primary">{derivedValue}</span>
        </span>
      )}
    </div>
  );
}

/* ──────────────────────────────── enum (property with options) ── */

const OTHER = "__other__";

function EnumField({ element, value, onChange, path }: FieldProps) {
  const id = `${path}-${element.id_short}`;
  const strVal = (value ?? "") as string;
  const startsAsOther = strVal !== "" && !(element.options ?? []).includes(strVal);
  const [otherMode, setOtherMode] = useState(startsAsOther);
  const [custom, setCustom] = useState(startsAsOther ? strVal : "");

  const handleSelect = (v: string) => {
    if (v === OTHER) {
      setOtherMode(true);
      onChange(custom || null);
    } else {
      setOtherMode(false);
      onChange(v === "" ? null : v);
    }
  };

  const handleCustom = (v: string) => {
    setCustom(v);
    onChange(v);
  };

  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-sm font-medium">
        {labelFor(element.id_short)}
        {element.description && (
          <span className="text-xs text-muted-foreground ml-1">
            — {element.description}
          </span>
        )}
      </label>
      <select
        id={id}
        className={inputClass()}
        value={otherMode ? OTHER : strVal}
        onChange={(e) => handleSelect(e.target.value)}
      >
        <option value="">— select —</option>
        {(element.options ?? []).map((opt) => (
          <option key={opt} value={opt}>{opt}</option>
        ))}
        <option value={OTHER}>Other (specify)…</option>
      </select>
      {otherMode && (
        <input
          type="text"
          placeholder="Enter custom value"
          className={inputClass()}
          value={custom}
          onChange={(e) => handleCustom(e.target.value)}
        />
      )}
    </div>
  );
}

/* ──────────────────────────────── reference_element ── */

function ReferenceField({ element, value, onChange, path }: FieldProps) {
  const id = `${path}-${element.id_short}`;
  const required = !isOptional(element.cardinality);
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-sm font-medium flex items-center gap-1.5 flex-wrap">
        {labelFor(element.id_short)}
        {required && <span className="text-destructive text-xs font-bold">*</span>}
        {" "}
        <span className="text-xs text-muted-foreground">(Reference URI)</span>
        {element.description && (
          <span className="text-xs text-muted-foreground">
            — {element.description}
          </span>
        )}
      </label>
      <input
        id={id}
        type="text"
        placeholder="https://..."
        className={inputClass()}
        value={String(value ?? "")}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  );
}

/* ──────────────────────────────── multi_language_property ── */

function MultiLangField({ element, value, onChange }: FieldProps) {
  const entries: LangEntry[] = Array.isArray(value)
    ? (value as LangEntry[])
    : [{ language: "en", text: "" }];

  const update = (index: number, key: keyof LangEntry, v: string) => {
    const next = entries.map((e, i) => (i === index ? { ...e, [key]: v } : e));
    onChange(next);
  };

  const addLang = () =>
    onChange([...entries, { language: "", text: "" }]);

  const removeLang = (index: number) =>
    onChange(entries.filter((_, i) => i !== index));

  return (
    <div className="flex flex-col gap-2">
      <span className="text-sm font-medium">
        {labelFor(element.id_short)}
        {element.description && (
          <span className="text-xs text-muted-foreground ml-1">
            — {element.description}
          </span>
        )}
      </span>
      {entries.map((entry, i) => (
        <div key={i} className="flex gap-2 items-center">
          <input
            type="text"
            placeholder="lang (e.g. en)"
            className={`${inputClass()} w-24`}
            value={entry.language}
            onChange={(e) => update(i, "language", e.target.value)}
          />
          <input
            type="text"
            placeholder="text"
            className={inputClass()}
            value={entry.text}
            onChange={(e) => update(i, "text", e.target.value)}
          />
          <button
            type="button"
            onClick={() => removeLang(i)}
            className="text-muted-foreground hover:text-destructive"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
      ))}
      <button
        type="button"
        onClick={addLang}
        className="flex items-center gap-1 text-xs text-primary hover:underline w-fit"
      >
        <Plus className="w-3 h-3" /> Add language
      </button>
    </div>
  );
}

/* ──────────────────────────────── list (SubmodelElementList) ── */

function ListField({ element, value, onChange }: FieldProps) {
  const items: string[] = Array.isArray(value) ? (value as string[]) : [];
  const [draft, setDraft] = useState("");

  const add = () => {
    if (draft.trim()) {
      onChange([...items, draft.trim()]);
      setDraft("");
    }
  };

  const remove = (i: number) => onChange(items.filter((_, idx) => idx !== i));

  return (
    <div className="flex flex-col gap-2">
      <span className="text-sm font-medium">
        {labelFor(element.id_short)}
        {element.description && (
          <span className="text-xs text-muted-foreground ml-1">
            — {element.description}
          </span>
        )}
      </span>
      <div className="flex flex-wrap gap-2">
        {items.map((item, i) => (
          <span
            key={i}
            className="inline-flex items-center gap-1 rounded-full bg-muted px-3 py-1 text-xs"
          >
            {item}
            <button
              type="button"
              onClick={() => remove(i)}
              className="text-muted-foreground hover:text-destructive"
            >
              ×
            </button>
          </span>
        ))}
      </div>
      <div className="flex gap-2">
        <input
          type="text"
          className={inputClass()}
          placeholder="Type and press Add…"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), add())}
        />
        <button
          type="button"
          onClick={add}
          className="rounded-md bg-primary text-primary-foreground px-3 py-2 text-sm hover:opacity-90"
        >
          Add
        </button>
      </div>
    </div>
  );
}

/* ──────────────────────────────── BOM reference list ── */

function BomRefListField({ element, value, onChange, bomEntries = [] }: FieldProps) {
  const selected = Array.isArray(value) ? (value as string[]) : [];
  const [draft, setDraft] = useState("");
  const available = bomEntries.filter((e) => !selected.includes(e.idShort));

  const add = (idShort: string) => {
    if (idShort && !selected.includes(idShort)) {
      onChange([...selected, idShort]);
      setDraft("");
    }
  };

  const remove = (idShort: string) =>
    onChange(selected.filter((s) => s !== idShort));

  return (
    <div className="flex flex-col gap-2">
      <span className="text-sm font-medium">
        {labelFor(element.id_short)}
        {element.description && (
          <span className="text-xs text-muted-foreground ml-1">
            — {element.description}
          </span>
        )}
      </span>
      <div className="flex flex-wrap gap-2">
        {selected.map((idShort) => {
          const entry = bomEntries.find((e) => e.idShort === idShort);
          return (
            <span
              key={idShort}
              className="inline-flex items-center gap-1 rounded-full bg-primary/10 text-primary px-3 py-1 text-xs font-mono"
            >
              {entry?.description ?? idShort}
              <button
                type="button"
                onClick={() => remove(idShort)}
                className="hover:text-destructive ml-1"
              >
                ×
              </button>
            </span>
          );
        })}
      </div>
      {bomEntries.length === 0 ? (
        <p className="text-xs text-muted-foreground italic px-1">
          No BOM entries available — fill the BillOfMaterials step first.
        </p>
      ) : (
        <div className="flex gap-2">
          <select
            className={inputClass()}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
          >
            <option value="">— select BOM entry —</option>
            {available.map((e) => (
              <option key={e.idShort} value={e.idShort}>
                {e.description}
              </option>
            ))}
          </select>
          <button
            type="button"
            disabled={!draft}
            onClick={() => add(draft)}
            className="rounded-md bg-primary text-primary-foreground px-3 py-2 text-sm hover:opacity-90 disabled:opacity-40"
          >
            Add
          </button>
        </div>
      )}
    </div>
  );
}

/* ──────────────────────────────── process step ref ── */

function ProcessStepRefField({ element, value, onChange, path, processStepEntries = [] }: FieldProps) {
  const id = `${path}-${element.id_short}`;
  const strVal = (value ?? "") as string;

  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-sm font-medium">
        {labelFor(element.id_short)}
        {element.description && (
          <span className="text-xs text-muted-foreground ml-1">— {element.description}</span>
        )}
      </label>
      {processStepEntries.length === 0 ? (
        <p className="text-xs text-muted-foreground italic px-1">
          No other steps defined yet — add more process steps first.
        </p>
      ) : (
        <select
          id={id}
          className={inputClass()}
          value={strVal}
          onChange={(e) => onChange(e.target.value || null)}
        >
          <option value="">— select step —</option>
          {processStepEntries.map((s) => (
            <option key={s.idShort} value={s.idShort}>{s.label}</option>
          ))}
        </select>
      )}
    </div>
  );
}

/* ──────────────────────────────── collection (recursive) ── */

function CollectionField({ element, value, onChange, path, context, inlineCapabilityMap, bomEntries, processStepEntries }: FieldProps) {
  const [open, setOpen] = useState(true);
  const optional = isOptional(element.cardinality);
  const hasPresetValue = value !== null && value !== undefined;
  const [enabled, setEnabled] = useState(!optional || hasPresetValue);

  const data = (value ?? {}) as FormData;

  const updateChild = (id_short: string, v: FormValue | FormData[]) => {
    onChange({ ...data, [id_short]: v });
  };

  // Extensible: array of FormData entries
  if (element.extensible) {
    const entries: FormData[] = Array.isArray(value) ? (value as FormData[]) : [];

    // If the only child is a non-extensible collection wrapper (e.g. BOMEntry inside
    // BOMEntries, ProcessStep inside ProcessSteps), render its children directly so
    // preset data stored as flat dicts maps correctly without an extra nesting level.
    const rawChildren = element.elements ?? [];
    const childElements =
      rawChildren.length === 1 &&
      rawChildren[0].type === "collection" &&
      !rawChildren[0].extensible
        ? (rawChildren[0].elements ?? [])
        : rawChildren;

    const addEntry = () => {
      const blank: FormData = {};
      onChange([...entries, blank]);
    };

    const removeEntry = (i: number) =>
      onChange(entries.filter((_, idx) => idx !== i));

    const updateEntry = (i: number, v: FormData) => {
      const next = entries.map((e, idx) => (idx === i ? v : e));
      onChange(next);
    };

    return (
      <div className="flex flex-col gap-2 border border-border rounded-lg p-3">
        <div
          className="flex items-center gap-2 cursor-pointer"
          onClick={() => setOpen(!open)}
        >
          {open ? (
            <ChevronDown className="w-4 h-4 text-muted-foreground" />
          ) : (
            <ChevronRight className="w-4 h-4 text-muted-foreground" />
          )}
          <span className="font-medium text-sm">
            {labelFor(element.id_short)}
          </span>
          <span className="text-xs text-muted-foreground">
            (extensible — {entries.length} entr{entries.length === 1 ? "y" : "ies"})
          </span>
        </div>

        {open && (
          <div className="flex flex-col gap-4 ml-4">
            {entries.map((entry, i) => {
              const operation = entry.Operation as string | undefined;
              const capElements = operation ? inlineCapabilityMap?.[operation] : undefined;
              return (
                <div
                  key={i}
                  className="border border-dashed border-border rounded-md p-3 flex flex-col gap-3 relative"
                >
                  <button
                    type="button"
                    onClick={() => removeEntry(i)}
                    className="absolute top-2 right-2 text-muted-foreground hover:text-destructive"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                  <span className="text-xs text-muted-foreground font-mono">
                    Entry {i + 1}
                  </span>
                  {childElements.map((child) => {
                    if (capElements && child.id_short === "RequiredCapabilityRef") {
                      return (
                        <div key={child.id_short} className="flex flex-col gap-1">
                          <span className="text-sm font-medium">RequiredCapabilityRef</span>
                          <span className="text-xs text-muted-foreground italic px-3 py-2 border border-border rounded-md bg-muted/30">
                            (auto-assigned from capability parameters below)
                          </span>
                        </div>
                      );
                    }
                    return (
                      <FieldRenderer
                        key={child.id_short}
                        element={child}
                        value={entry[child.id_short] as FormValue}
                        onChange={(v) =>
                          updateEntry(i, { ...entry, [child.id_short]: v })
                        }
                        path={`${path}-${element.id_short}-${i}`}
                        context={context}
                        inlineCapabilityMap={inlineCapabilityMap}
                        bomEntries={bomEntries}
                        processStepEntries={processStepEntries}
                      />
                    );
                  })}
                  {capElements && (
                    <div className="border-l-2 border-primary/40 pl-4 flex flex-col gap-3 mt-1">
                      <span className="text-xs font-semibold text-primary uppercase tracking-wide">
                        Capability Parameters — {operation}
                      </span>
                      {capElements.map((capEl) => (
                        <FieldRenderer
                          key={capEl.id_short}
                          element={capEl}
                          value={((entry.CapabilityParams as FormData) ?? {})[capEl.id_short] as FormValue}
                          onChange={(v) =>
                            updateEntry(i, {
                              ...entry,
                              CapabilityParams: {
                                ...((entry.CapabilityParams as FormData) ?? {}),
                                [capEl.id_short]: v,
                              },
                            })
                          }
                          path={`${path}-${element.id_short}-${i}-cap`}
                          context={context}
                          inlineCapabilityMap={inlineCapabilityMap}
                          bomEntries={bomEntries}
                        />
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
            <button
              type="button"
              onClick={addEntry}
              className="flex items-center gap-1 text-sm text-primary hover:underline w-fit"
            >
              <Plus className="w-4 h-4" />
              Add{" "}
              {element.entry_template
                ? element.entry_template.replace("{N}", String(entries.length + 1))
                : "entry"}
            </button>
          </div>
        )}
      </div>
    );
  }

  // Non-extensible collection
  return (
    <div className="flex flex-col gap-2 border border-border rounded-lg p-3">
      <div className="flex items-center gap-2">
        {optional && (
          <input
            type="checkbox"
            className="w-4 h-4 accent-primary"
            checked={enabled}
            onChange={(e) => setEnabled(e.target.checked)}
          />
        )}
        <div
          className={`flex items-center gap-2 ${optional ? "cursor-pointer" : ""} flex-1`}
          onClick={() => setOpen(!open)}
        >
          {open ? (
            <ChevronDown className="w-4 h-4 text-muted-foreground" />
          ) : (
            <ChevronRight className="w-4 h-4 text-muted-foreground" />
          )}
          <span className="font-medium text-sm">
            {labelFor(element.id_short)}
          </span>
          {optional && (
            <span className="text-xs text-muted-foreground">(optional)</span>
          )}
        </div>
      </div>

      {open && (!optional || enabled) && (
        <div className="flex flex-col gap-4 ml-4 mt-1">
          {(element.elements ?? []).map((child) => (
            <FieldRenderer
              key={child.id_short}
              element={child}
              value={data[child.id_short] as FormValue}
              onChange={(v) => updateChild(child.id_short, v)}
              path={`${path}-${element.id_short}`}
              context={context}
              inlineCapabilityMap={inlineCapabilityMap}
              bomEntries={bomEntries}
              processStepEntries={processStepEntries}
            />
          ))}
        </div>
      )}
    </div>
  );
}

/* ──────────────────────────────── dispatcher ── */

export function FieldRenderer({ element, value, onChange, path, context, inlineCapabilityMap, bomEntries, processStepEntries }: FieldProps) {
  const optional = isOptional(element.cardinality);
  const hasPresetValue = value !== null && value !== undefined;
  const [enabled, setEnabled] = useState(!optional || hasPresetValue);
  // keeps the last non-null value so toggling off then on restores it
  const savedValue = useRef<FormValue | FormData[]>(value);

  // collections handle their own optional toggle
  if (element.type === "collection") {
    return (
      <CollectionField
        element={element}
        value={value}
        onChange={onChange}
        path={path}
        context={context}
        inlineCapabilityMap={inlineCapabilityMap}
        bomEntries={bomEntries}
        processStepEntries={processStepEntries}
      />
    );
  }

  const wrap = (inner: React.ReactNode) => {
    if (!optional) return <>{inner}</>;
    return (
      <div className="flex gap-2 items-start">
        <input
          type="checkbox"
          className="mt-2 w-4 h-4 accent-primary"
          checked={enabled}
          onChange={(e) => {
            const nowEnabled = e.target.checked;
            setEnabled(nowEnabled);
            if (!nowEnabled) {
              savedValue.current = value; // save before clearing
              onChange(null);
            } else {
              onChange(savedValue.current); // restore on re-enable
            }
          }}
        />
        <div className={`flex-1 ${!enabled ? "opacity-40 pointer-events-none" : ""}`}>
          {inner}
        </div>
      </div>
    );
  };

  if (element.type === "property" && element.ref_source === "process_steps") {
    return wrap(
      <ProcessStepRefField
        element={element}
        value={value}
        onChange={onChange}
        path={path}
        processStepEntries={processStepEntries}
      />
    );
  }

  if (element.type === "property" && element.options && element.options.length > 0) {
    return wrap(
      <EnumField
        element={element}
        value={value}
        onChange={onChange}
        path={path}
        context={context}
      />
    );
  }

  if (element.type === "property") {
    return wrap(
      <PropertyField
        element={element}
        value={value}
        onChange={onChange}
        path={path}
        context={context}
      />
    );
  }

  if (element.type === "reference_element") {
    return wrap(
      <ReferenceField
        element={element}
        value={value}
        onChange={onChange}
        path={path}
        context={context}
      />
    );
  }

  if (element.type === "multi_language_property") {
    return wrap(
      <MultiLangField
        element={element}
        value={value}
        onChange={onChange}
        path={path}
        context={context}
      />
    );
  }

  if (element.type === "list" && element.element_type === "reference_element") {
    return wrap(
      <BomRefListField
        element={element}
        value={value}
        onChange={onChange}
        path={path}
        bomEntries={bomEntries}
      />
    );
  }

  if (element.type === "list") {
    return wrap(
      <ListField
        element={element}
        value={value}
        onChange={onChange}
        path={path}
      />
    );
  }

  // Fallback: render as text
  return wrap(
    <PropertyField
      element={{ ...element, value_type: "xs:string" }}
      value={value}
      onChange={onChange}
      path={path}
    />
  );
}
