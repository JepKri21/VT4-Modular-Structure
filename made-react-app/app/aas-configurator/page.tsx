"use client";

import React, { useCallback, useEffect, useState } from "react";
import { FieldRenderer } from "@/components/aas-configurator/FieldRenderer";
import {
  BomEntry,
  FormData,
  FormValue,
  OperationCapability,
  ProcessStepEntry,
  ShellCategory,
  ShellPreset,
  ShellPresetSummary,
  ShellSubmodelSlot,
  ShellType,
  SubmodelTemplate,
  TemplateElement,
  mergePresetIntoForm,
  flattenFormData,
  applyDerivedFields,
  computeBomEntryIdShort,
  computeStepIdShort,
} from "@/components/aas-configurator/types";
import {
  ArrowLeft,
  ArrowRight,
  Check,
  ChevronDown,
  ChevronRight,
  Download,
  FileJson,
  Layers,
  PackagePlus,
  RefreshCw,
  ShoppingCart,
  Sparkles,
  PlusCircle,
  Upload,
  AlertCircle,
  Settings,
  FolderOpen,
} from "lucide-react";

/* ─────────────────────────────────────── helpers ── */

function inputClass() {
  return "w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary";
}

function applyPattern(pattern: string, name: string, category: string, uuid?: string) {
  return pattern
    .replace(/\{name\}/g, name || "MyAsset")
    .replace(/\{asset_name\}/g, name || "MyAsset")
    .replace(/\{category\}/g, category || "General")
    .replace(/\{asset_type\}/g, category || "General")
    .replace(/\{uuid\}/g, uuid ?? "{uuid}");
}

function buildSubmodelId(instanceShellId: string, slot: ShellSubmodelSlot) {
  return `${instanceShellId}/${slot.id_short}`;
}


type CapabilitySubmodelInput = {
  template_file: string;
  id_short: string;
  id: string;
  form_data: FormData;
};

type BatchResult = {
  presetFilename: string;
  presetLabel: string;
  shellLabel: string;
  quantity: number;
  succeeded: number;
  ok: boolean;
  errors: string[];
};

function resolveBopForGeneration(
  formData: FormData,
  operations: Record<string, OperationCapability>,
  instanceShellId: string,
  baseSubmodelCount: number,
  bomSubmodelId?: string,
): { bopData: FormData; capabilitySubmodels: CapabilitySubmodelInput[] } {
  const rawSteps = formData.ProcessSteps;
  if (!Array.isArray(rawSteps) || rawSteps.length === 0)
    return { bopData: formData, capabilitySubmodels: [] };

  const capabilitySubmodels: CapabilitySubmodelInput[] = [];

  const resolveComponents = (ids: string[]) =>
    bomSubmodelId
      ? ids.map((idShort) => ({ submodel_id: bomSubmodelId, path: ["BOMEntries", idShort] }))
      : ids;

  const resolvedSteps = rawSteps.map((rawStep) => {
    if (!rawStep || typeof rawStep !== "object" || Array.isArray(rawStep))
      return rawStep as FormData;

    const step = rawStep as FormData;
    const op = typeof step.Operation === "string" ? step.Operation : "";
    const cap = operations[op];
    const capParams = step.CapabilityParams as FormData | undefined;

    // Strip CapabilityParams — not part of the BOP submodel schema the Python script expects
    const { CapabilityParams: _dropped, ...stepWithoutCap } = step as Record<string, unknown>;

    const rawComponents = Array.isArray(step.RequiredComponents) ? (step.RequiredComponents as string[]) : [];
    const resolvedStep = { ...stepWithoutCap, RequiredComponents: resolveComponents(rawComponents) };

    if (!cap || !capParams) return resolvedStep as FormData;

    const capIdx = capabilitySubmodels.length;
    const idShort = `${cap.id_short}_${capIdx}`;
    const submodelIdx = baseSubmodelCount + capIdx;
    const submodelId = `${instanceShellId}/Submodel/${idShort}/${submodelIdx}`;

    capabilitySubmodels.push({
      template_file: cap.template_file,
      id_short: idShort,
      id: submodelId,
      form_data: capParams,
    });

    return { ...resolvedStep, RequiredCapabilityRef: submodelId } as FormData;
  });

  return {
    bopData: { ...formData, ProcessSteps: resolvedSteps as FormData[] },
    capabilitySubmodels,
  };
}

/* ─────────────────────────────────────── step bar ── */

type WizardStep =
  | { kind: "shell-select" }
  | { kind: "instance-info" }
  | { kind: "submodel"; index: number }
  | { kind: "review" };

function StepBar({
  current,
  shellType,
}: {
  current: WizardStep;
  shellType: ShellType | null;
}) {
  const steps: WizardStep[] = [
    { kind: "shell-select" },
    { kind: "instance-info" },
    ...(shellType?.submodels.map((_, i) => ({
      kind: "submodel" as const,
      index: i,
    })) ?? []),
    { kind: "review" },
  ];

  const labels = [
    "Select Shell",
    "Instance Info",
    ...(shellType?.submodels.map((s) => s.id_short) ?? []),
    "Export",
  ];

  const currentIdx = steps.findIndex((s) => {
    if (s.kind !== current.kind) return false;
    if (s.kind === "submodel" && current.kind === "submodel")
      return s.index === current.index;
    return true;
  });

  return (
    <div className="flex items-center gap-0 mb-8 overflow-x-auto pb-2">
      {steps.map((_, i) => {
        const done = i < currentIdx;
        const active = i === currentIdx;
        return (
          <React.Fragment key={i}>
            <div className="flex flex-col items-center gap-1 shrink-0">
              <div
                className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold
                  ${done ? "bg-primary text-primary-foreground" : active ? "bg-primary/20 text-primary border-2 border-primary" : "bg-muted text-muted-foreground"}`}
              >
                {done ? <Check className="w-3 h-3" /> : i + 1}
              </div>
              <span
                className={`text-xs whitespace-nowrap max-w-[80px] text-center leading-tight
                  ${active ? "text-primary font-semibold" : "text-muted-foreground"}`}
              >
                {labels[i]}
              </span>
            </div>
            {i < steps.length - 1 && (
              <div
                className={`h-0.5 flex-1 min-w-4 mx-1 mb-4 shrink ${done ? "bg-primary" : "bg-border"}`}
              />
            )}
          </React.Fragment>
        );
      })}
    </div>
  );
}

/* ─────────────────────────────────────── shell card ── */

function ShellCard({
  shell,
  selected,
  selectedCategory,
  onClick,
  onCategorySelect,
}: {
  shell: ShellType;
  selected: boolean;
  selectedCategory: ShellCategory | null;
  onClick: () => void;
  onCategorySelect: (cat: ShellCategory | null) => void;
}) {
  return (
    <div
      className={`rounded-xl border-2 transition-all
        ${selected ? "border-primary bg-primary/5" : "border-border bg-card"}`}
    >
      <button
        type="button"
        onClick={onClick}
        className="text-left w-full p-4"
      >
        <div className="flex items-start justify-between gap-2">
          <div className="flex flex-col gap-2">
            <div className="flex items-center gap-2">
              <span className="font-semibold text-sm">{shell.label}</span>
              <span className="text-xs rounded-full bg-muted px-2 py-0.5 text-muted-foreground">
                {shell.kind}
              </span>
            </div>
            {shell.description && (
              <p className="text-xs text-muted-foreground leading-relaxed">
                {shell.description}
              </p>
            )}
            <div className="flex flex-wrap gap-1 mt-1">
              {shell.submodels.map((sm) => (
                <span
                  key={sm.template_id}
                  className={`text-xs rounded-full px-2 py-0.5 font-mono
                    ${sm.required ? "bg-primary/10 text-primary" : "bg-muted text-muted-foreground"}`}
                  title={sm.required ? "required" : "optional"}
                >
                  {sm.id_short}
                </span>
              ))}
            </div>
          </div>
          {selected && <Check className="w-4 h-4 text-primary shrink-0 mt-1" />}
        </div>
      </button>

      {/* category picker — expands inline when this shell is selected and has categories */}
      {selected && shell.categories.length > 0 && (
        <div className="border-t border-primary/20 px-4 py-3 flex flex-col gap-2">
          <p className="text-xs text-muted-foreground font-medium">Choose a category</p>
          <div className="flex flex-wrap gap-2">
            {shell.categories.map((cat) => (
              <button
                key={cat.name}
                type="button"
                onClick={() => onCategorySelect(selectedCategory?.name === cat.name ? null : cat)}
                className={`rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors ${
                  selectedCategory?.name === cat.name
                    ? "border-primary bg-primary text-primary-foreground"
                    : "border-border bg-background hover:bg-muted"
                }`}
              >
                {cat.label}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/* ─────────────────────────────────────── preset card ── */

function PresetCard({
  preset,
  selected,
  onClick,
}: {
  preset: ShellPresetSummary;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`text-left w-full rounded-xl border-2 p-4 transition-all
        ${selected ? "border-primary bg-primary/5" : "border-border hover:border-primary/50 bg-card"}`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-2">
            <Sparkles className="w-3.5 h-3.5 text-primary shrink-0" />
            <span className="font-semibold text-sm">{preset.label}</span>
          </div>
          {preset.description && (
            <p className="text-xs text-muted-foreground leading-relaxed">
              {preset.description}
            </p>
          )}
          {(preset.asset_name || preset.asset_category) && (
            <div className="flex gap-2 mt-1">
              {preset.asset_name && (
                <span className="text-xs rounded-full bg-muted px-2 py-0.5 font-mono text-muted-foreground">
                  {preset.asset_name}
                </span>
              )}
              {preset.asset_category && (
                <span className="text-xs rounded-full bg-muted px-2 py-0.5 text-muted-foreground">
                  {preset.asset_category}
                </span>
              )}
            </div>
          )}
        </div>
        {selected && <Check className="w-4 h-4 text-primary shrink-0 mt-1" />}
      </div>
    </button>
  );
}

/* ─────────────────────────────────────── submodel progress ── */

function SubmodelProgress({
  slots,
  currentIndex,
  filledSlots,
}: {
  slots: ShellSubmodelSlot[];
  currentIndex: number;
  filledSlots: Set<number>;
}) {
  return (
    <div className="flex flex-col gap-1 mb-6 p-3 rounded-lg bg-muted/50 border border-border">
      <span className="text-xs text-muted-foreground font-medium mb-1">
        Submodels in this shell
      </span>
      {slots.map((slot, i) => {
        const done = i < currentIndex || filledSlots.has(i);
        const active = i === currentIndex;
        return (
          <div key={i} className="flex items-center gap-2">
            <div
              className={`w-5 h-5 rounded-full flex items-center justify-center shrink-0
              ${done ? "bg-primary text-primary-foreground" : active ? "bg-primary/20 border-2 border-primary" : "bg-muted border border-border"}`}
            >
              {done ? (
                <Check className="w-3 h-3" />
              ) : (
                <span className="text-[10px]">{i + 1}</span>
              )}
            </div>
            <span
              className={`text-xs font-mono flex-1 ${active ? "text-primary font-semibold" : done ? "text-foreground" : "text-muted-foreground"}`}
            >
              {slot.id_short}
            </span>
            {!slot.required && (
              <span className="text-[10px] text-muted-foreground">optional</span>
            )}
            {active && <span className="text-xs text-primary">← current</span>}
          </div>
        );
      })}
    </div>
  );
}

/* ─────────────────────────────────────── json output ── */

function JsonOutput({
  label,
  data,
}: {
  label: string;
  data: Record<string, unknown>;
}) {
  const json = JSON.stringify(data, null, 2);
  const download = () => {
    const blob = new Blob([json], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${label}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold flex items-center gap-2">
          <FileJson className="w-4 h-4" />
          {label}
        </span>
        <button
          type="button"
          onClick={download}
          className="flex items-center gap-1 rounded-md bg-primary text-primary-foreground px-3 py-1.5 text-xs hover:opacity-90"
        >
          <Download className="w-3 h-3" />
          Download
        </button>
      </div>
      <pre className="rounded-lg bg-muted border border-border text-xs p-4 overflow-auto max-h-96 font-mono">
        {json}
      </pre>
    </div>
  );
}

/* ─────────────────────────────────────── page ── */

export default function AasConfiguratorPage() {
  const [step, setStep] = useState<WizardStep>({ kind: "shell-select" });

  // Shell selection
  const [shellTypes, setShellTypes] = useState<ShellType[]>([]);
  const [loadingShells, setLoadingShells] = useState(true);
  const [selectedShell, setSelectedShell] = useState<ShellType | null>(null);

  // Capability slots injected dynamically based on BOP operations
  const [extraSlots, setExtraSlots] = useState<ShellSubmodelSlot[]>([]);
  // Operation → capability mapping loaded from BOP template
  const [bopOperations, setBopOperations] = useState<Record<string, OperationCapability>>({});
  // Fetched capability templates keyed by template_file name
  const [capabilityTemplates, setCapabilityTemplates] = useState<Record<string, SubmodelTemplate>>({});

  // Preset selection (shown on the same shell-select step)
  const [presets, setPresets] = useState<ShellPresetSummary[]>([]);
  const [loadingPresets, setLoadingPresets] = useState(false);
  const [selectedPreset, setSelectedPreset] =
    useState<ShellPresetSummary | null>(null);
  const [selectedCategory, setSelectedCategory] = useState<ShellCategory | null>(null);
  const [presetApplied, setPresetApplied] = useState(false);
  const [presetIncludes, setPresetIncludes] = useState<Record<string, string[]> | null>(null);

  // Active shell: base shell slots + any capability slots injected from BOP operations.
  // When a category is selected and has its own submodels (e.g. drilling_station defines
  // DrillingCapabilityOffered rather than the generic CapabilitiesOffered from resource_shell),
  // those category-specific slots replace the abstract blueprint slots so preset data matches.
  const activeShell = React.useMemo<ShellType | null>(() => {
    if (!selectedShell) return null;
    const base: ShellType =
      selectedCategory?.submodels && selectedCategory.submodels.length > 0
        ? { ...selectedShell, submodels: selectedCategory.submodels }
        : selectedShell;
    if (extraSlots.length === 0) return base;
    return { ...base, submodels: [...base.submodels, ...extraSlots] };
  }, [selectedShell, selectedCategory, extraSlots]);

  // Instance info
  const [assetName, setAssetName] = useState("");
  const [assetCategory, setAssetCategory] = useState("");
  const [quantity, setQuantity] = useState(1);
  const shellId = selectedShell
    ? applyPattern(selectedShell.id_pattern, assetName, assetCategory)
    : "";
  const globalAssetId = selectedShell
    ? applyPattern(
        selectedShell.global_asset_id_pattern,
        assetName,
        assetCategory
      )
    : "";

  // Submodel filling
  const [loadedTemplates, setLoadedTemplates] = useState<
    Record<number, SubmodelTemplate>
  >({});
  const [submodelForms, setSubmodelForms] = useState<Record<number, FormData>>(
    {}
  );
  const [loadingTemplate, setLoadingTemplate] = useState(false);
  const [filledSlots, setFilledSlots] = useState<Set<number>>(new Set());

  // Review — one environment object per generated instance
  const [aasInstances, setAasInstances] =
    useState<Record<string, unknown>[] | null>(null);

  // Save as preset
  const [presetSaveLabel, setPresetSaveLabel] = useState("");
  const [presetSaveDesc, setPresetSaveDesc] = useState("");
  const [presetSaveState, setPresetSaveState] = useState<"idle" | "saving" | "saved" | "error">("idle");

  // Python generation
  const [generating, setGenerating] = useState(false);
  const [generateError, setGenerateError] = useState<string | null>(null);

  // Batch generator
  const [batchOpen, setBatchOpen] = useState(false);
  const [allPresets, setAllPresets] = useState<Record<string, ShellPresetSummary[]>>({});
  const [allPresetsLoading, setAllPresetsLoading] = useState(false);
  const [batchQuantities, setBatchQuantities] = useState<Record<string, number>>({});
  const [batchGenerating, setBatchGenerating] = useState(false);
  const [batchResults, setBatchResults] = useState<BatchResult[]>([]);
  const [batchServerUrl, setBatchServerUrl] = useState("http://localhost:8081");

  // Settings
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [generatorPath, setGeneratorPath] = useState("");
  const [pathSaveState, setPathSaveState] = useState<"idle" | "saving" | "saved" | "error">("idle");

  useEffect(() => {
    fetch("/api/aas-configurator/config")
      .then((r) => r.json())
      .then((d: { generatorPath?: string }) => { if (d.generatorPath) setGeneratorPath(d.generatorPath); })
      .catch(() => {});
  }, []);

  const saveGeneratorPath = async () => {
    setPathSaveState("saving");
    try {
      const res = await fetch("/api/aas-configurator/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ generatorPath }),
      });
      if (!res.ok) throw new Error(await res.text());
      setPathSaveState("saved");
      setSelectedShell(null);
      setAllPresets({});
      setStep({ kind: "shell-select" });
      fetchShellTypes();
    } catch {
      setPathSaveState("error");
    }
  };

  // Upload to BaSyx
  const [serverUrl, setServerUrl] = useState("http://localhost:8081");
  type UploadResult = { type: string; id: string; status: number; ok: boolean; error?: string };
  const [uploadResults, setUploadResults] = useState<Record<number, UploadResult[]>>({});
  const [uploadState, setUploadState] = useState<Record<number, "idle" | "uploading" | "done" | "error">>({});

  const fetchShellTypes = useCallback(() => {
    setLoadingShells(true);
    fetch("/api/aas-configurator/shell-types")
      .then((r) => r.json())
      .then((data) => {
        setShellTypes(Array.isArray(data) ? data : []);
        setLoadingShells(false);
      })
      .catch(() => setLoadingShells(false));
  }, []);

  /* fetch shell types once */
  useEffect(() => {
    fetchShellTypes();
  }, [fetchShellTypes]);

  /* fetch presets when a shell or category is selected */
  useEffect(() => {
    if (!selectedShell) return;
    setLoadingPresets(true);
    setSelectedPreset(null);
    setPresetApplied(false);
    const filter = selectedCategory ? selectedCategory.name : selectedShell.name;
    fetch(`/api/aas-configurator/presets?shell=${filter}`)
      .then((r) => r.json())
      .then((data) => {
        setPresets(Array.isArray(data) ? data : []);
        setLoadingPresets(false);
      })
      .catch(() => setLoadingPresets(false));
  }, [selectedShell, selectedCategory]);

  /* load all presets for all shell types when the batch panel is opened (cached) */
  useEffect(() => {
    if (!batchOpen || shellTypes.length === 0 || Object.keys(allPresets).length > 0) return;
    setAllPresetsLoading(true);
    Promise.all(
      shellTypes.map((shell) =>
        fetch(`/api/aas-configurator/presets?shell=${shell.name}`)
          .then((r) => r.json())
          .then((data: ShellPresetSummary[]) => ({ shellName: shell.name, presets: Array.isArray(data) ? data : [] }))
          .catch(() => ({ shellName: shell.name, presets: [] as ShellPresetSummary[] }))
      )
    ).then((results) => {
      const map: Record<string, ShellPresetSummary[]> = {};
      results.forEach(({ shellName, presets }) => { if (presets.length > 0) map[shellName] = presets; });
      setAllPresets(map);
      setAllPresetsLoading(false);
    });
  }, [batchOpen, shellTypes, allPresets]);

  /* load submodel template by slot index (cached) */
  const loadTemplateForSlot = useCallback(
    async (index: number, slot: ShellSubmodelSlot) => {
      if (loadedTemplates[index]) return loadedTemplates[index];
      if (!slot.template_file) return null;
      setLoadingTemplate(true);
      try {
        const res = await fetch(
          `/api/aas-configurator/templates/${slot.template_file}`
        );
        const data = (await res.json()) as SubmodelTemplate;
        setLoadedTemplates((prev) => ({ ...prev, [index]: data }));
        if (data.operations && Object.keys(data.operations).length > 0) {
          setBopOperations(data.operations);
        }
        setLoadingTemplate(false);
        return data;
      } catch {
        setLoadingTemplate(false);
        return null;
      }
    },
    [loadedTemplates]
  );

  /* watch BOP form data — fetch capability templates for operations in use */
  const bopSlotIndex = activeShell?.submodels.findIndex(
    (s) => s.template_file === "sub_assembly_bop"
  ) ?? -1;

  const bomSlotIndex = activeShell?.submodels.findIndex(
    (s) => s.id_short === "BillOfMaterials"
  ) ?? -1;

  const bomEntries: BomEntry[] = React.useMemo(() => {
    if (bomSlotIndex < 0) return [];
    const entries = ((submodelForms[bomSlotIndex] ?? {}).BOMEntries ?? []) as FormData[];
    return entries.map((entry, i) => ({
      idShort: computeBomEntryIdShort(entry, i),
      description: String(entry.Description ?? `Entry ${i + 1}`),
    }));
  }, [bomSlotIndex, submodelForms]);

  const processStepEntries: ProcessStepEntry[] = React.useMemo(() => {
    if (bopSlotIndex < 0) return [];
    const steps = ((submodelForms[bopSlotIndex] ?? {}).ProcessSteps ?? []) as FormData[];
    return steps.map((step, i) => {
      const idShort = computeStepIdShort(step, i);
      const op = String(step.Operation ?? "");
      return { idShort, label: op ? `${op} (${idShort})` : idShort };
    });
  }, [bopSlotIndex, submodelForms]);

  useEffect(() => {
    if (bopSlotIndex < 0 || Object.keys(bopOperations).length === 0) return;
    const bopData = (submodelForms[bopSlotIndex] ?? {}) as FormData;
    const steps = (bopData.ProcessSteps ?? []) as FormData[];
    if (steps.length === 0) return;

    // Fetch capability templates for any new operations not yet cached
    const usedOps = [...new Set(steps.map((s) => s.Operation as string).filter(Boolean))];
    usedOps.forEach(async (op) => {
      const cap = bopOperations[op];
      if (!cap) return;
      setCapabilityTemplates((prev) => {
        if (prev[cap.template_file]) return prev; // already cached
        // Fetch asynchronously and update state when done
        fetch(`/api/aas-configurator/templates/${cap.template_file}`)
          .then((r) => r.json())
          .then((data: SubmodelTemplate) => {
            setCapabilityTemplates((p) =>
              p[cap.template_file] ? p : { ...p, [cap.template_file]: data }
            );
          })
          .catch(() => {});
        return prev;
      });
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(submodelForms[bopSlotIndex]), bopOperations]);

  /* apply preset: fetch full preset data and merge into all submodel forms */
  const applyPreset = async (presetSummary: ShellPresetSummary) => {
    if (!activeShell) return;
    const res = await fetch(
      `/api/aas-configurator/presets/${presetSummary.filename}`
    );
    const preset = (await res.json()) as ShellPreset;

    // pre-fill asset name / category
    if (preset.asset_name) setAssetName(preset.asset_name);
    if (preset.asset_category) setAssetCategory(preset.asset_category);

    // merge preset submodel data into form state, keyed by slot id_short
    if (preset.submodels) {
      setSubmodelForms((prev) => {
        const next = { ...prev };
        activeShell.submodels.forEach((slot, i) => {
          const presetSlotData = preset.submodels[slot.id_short] as
            | Record<string, unknown>
            | undefined;
          if (presetSlotData) {
            next[i] = mergePresetIntoForm(prev[i] ?? {}, presetSlotData);
          }
        });
        return next;
      });
    }
    setPresetIncludes((preset.include as Record<string, string[]>) ?? null);
    setPresetApplied(true);
  };

  /* current slot info */
  const currentIndex = step.kind === "submodel" ? step.index : -1;
  const currentSlot =
    step.kind === "submodel" && activeShell
      ? activeShell.submodels[step.index]
      : null;
  const currentTemplate =
    step.kind === "submodel" ? loadedTemplates[step.index] : null;
  const currentFormData =
    step.kind === "submodel" ? (submodelForms[step.index] ?? {}) : {};

  const updateCurrentField = (id_short: string, v: FormValue | FormData[]) => {
    if (step.kind !== "submodel") return;
    const idx = step.index;
    setSubmodelForms((prev) => ({
      ...prev,
      [idx]: { ...(prev[idx] ?? {}), [id_short]: v },
    }));
  };

  /* ── transitions ── */

  const goToSubmodel = async (index: number) => {
    if (!activeShell) return;
    const slot = activeShell.submodels[index];
    await loadTemplateForSlot(index, slot);
    setStep({ kind: "submodel", index });
  };

  const markCurrentFilled = () => {
    if (step.kind !== "submodel") return;
    setFilledSlots((prev) => new Set(prev).add(step.index));
  };

  const goNext = async () => {
    if (!activeShell) return;
    if (step.kind === "shell-select") {
      setStep({ kind: "instance-info" });
      return;
    }
    if (step.kind === "instance-info") {
      await goToSubmodel(0);
      return;
    }
    if (step.kind !== "submodel") return;
    markCurrentFilled();
    const nextIndex = step.index + 1;
    if (nextIndex >= activeShell.submodels.length) {
      await buildEnvironment();
      setStep({ kind: "review" });
    } else {
      await goToSubmodel(nextIndex);
    }
  };

  const goBack = async () => {
    if (step.kind === "instance-info") {
      setStep({ kind: "shell-select" });
    } else if (step.kind === "submodel") {
      if (step.index === 0) {
        setStep({ kind: "instance-info" });
      } else {
        await goToSubmodel(step.index - 1);
      }
    } else if (step.kind === "review" && activeShell) {
      setStep({ kind: "submodel", index: activeShell.submodels.length - 1 });
    }
  };

  const createWithPreset = async () => {
    if (!activeShell) return;
    const results = await Promise.all(
      activeShell.submodels.map((slot, i) => loadTemplateForSlot(i, slot))
    );
    const templateMap: Record<number, SubmodelTemplate> = {};
    const freshOperations: Record<string, OperationCapability> = {};
    results.forEach((t, i) => {
      if (!t) return;
      templateMap[i] = t;
      if (t.operations) Object.assign(freshOperations, t.operations);
    });
    setFilledSlots(new Set(activeShell.submodels.map((_, i) => i)));
    await buildEnvironment(templateMap, freshOperations);
    setStep({ kind: "review" });
  };

  const saveAsPreset = async () => {
    if (!activeShell || !presetSaveLabel.trim()) return;
    setPresetSaveState("saving");
    const submodels: Record<string, unknown> = {};
    activeShell.submodels.forEach((slot, i) => {
      submodels[slot.id_short] = submodelForms[i] ?? {};
    });
    const filename = presetSaveLabel.trim().toLowerCase().replace(/\s+/g, "_");
    try {
      const res = await fetch("/api/aas-configurator/presets", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          shell: selectedShell!.name,
          label: presetSaveLabel.trim(),
          description: presetSaveDesc.trim(),
          asset_name: assetName,
          asset_category: assetCategory,
          submodels,
          filename,
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      setPresetSaveState("saved");
    } catch {
      setPresetSaveState("error");
    }
  };

  const buildEnvironment = async (templateOverride?: Record<number, SubmodelTemplate>, operationsOverride?: Record<string, OperationCapability>) => {
    if (!activeShell) return;
    setGenerating(true);
    setGenerateError(null);
    try {
      const templates = templateOverride ?? loadedTemplates;
      const instances = await Promise.all(
        Array.from({ length: quantity }, async () => {
          const uuid = crypto.randomUUID();
          const instanceShellId = applyPattern(selectedShell!.id_pattern, assetName, assetCategory, uuid);
          const instanceGlobalAssetId = applyPattern(selectedShell!.global_asset_id_pattern, assetName, assetCategory, uuid);

          let capabilitySubmodelInputs: CapabilitySubmodelInput[] = [];

          const bomSlotIdx = activeShell.submodels.findIndex((s) => s.id_short === "BillOfMaterials");
          const bomSubmodelId = bomSlotIdx >= 0
            ? buildSubmodelId(instanceShellId, activeShell.submodels[bomSlotIdx])
            : undefined;

          const baseInputs = activeShell.submodels
            .map((slot, i) => {
              const template = templates[i];
              if (!template) return null;
              const rawForm = submodelForms[i] ?? {};
              const derivedCtx = {
                AssetName: assetName,
                AssetCategory: assetCategory,
                ...flattenFormData(rawForm),
              };
              const withDerived = applyDerivedFields(
                template.elements,
                rawForm,
                derivedCtx
              );

              let formData = withDerived;
              if (slot.template_file === "sub_assembly_bop") {
                const result = resolveBopForGeneration(
                  withDerived,
                  operationsOverride ?? bopOperations,
                  instanceShellId,
                  activeShell.submodels.length,
                  bomSubmodelId,
                );
                formData = result.bopData;
                capabilitySubmodelInputs = result.capabilitySubmodels;
              }

              return {
                template_file: slot.template_file,
                id_short: slot.id_short,
                id: buildSubmodelId(instanceShellId, slot),
                form_data: formData,
              };
            })
            .filter(Boolean);

          const submodelInputs = [...baseInputs, ...capabilitySubmodelInputs];

          const res = await fetch("/api/aas-configurator/generate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              shell_type: activeShell.name,
              name: assetName,
              category: assetCategory,
              shell_id: instanceShellId,
              global_asset_id: instanceGlobalAssetId,
              submodels: submodelInputs,
            }),
          });

          if (!res.ok) {
            const err = await res.json() as { error?: string };
            throw new Error(err.error ?? `Generation failed (${res.status})`);
          }
          return res.json() as Promise<Record<string, unknown>>;
        })
      );
      setAasInstances(instances);
    } catch (err) {
      setGenerateError(String(err));
    } finally {
      setGenerating(false);
    }
  };

  const uploadToBaSyx = async (env: Record<string, unknown>, idx: number) => {
    if (!selectedShell) return;
    setUploadState((prev) => ({ ...prev, [idx]: "uploading" }));
    setUploadResults((prev) => ({ ...prev, [idx]: [] }));
    const shell = (env.assetAdministrationShells as Record<string, unknown>[])[0];
    const submodels = env.submodels as Record<string, unknown>[];
    try {
      const res = await fetch("/api/aas-configurator/upload", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ serverUrl, shell, submodels }),
      });
      const data = await res.json() as { results: UploadResult[] };
      setUploadResults((prev) => ({ ...prev, [idx]: data.results }));
      const allOk = data.results.every((r) => r.ok);
      setUploadState((prev) => ({ ...prev, [idx]: allOk ? "done" : "error" }));
      if (allOk) {
        const assetInfo = (shell.assetInformation ?? {}) as Record<string, unknown>;
        fetch("/api/inventory", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            id: shell.id,
            globalAssetId: (assetInfo.globalAssetId as string) ?? "",
            name: assetName,
            category: assetCategory,
            shellTypeName: selectedShell!.name,
            serverUrl,
          }),
        }).catch(() => {});
      }
    } catch (err) {
      setUploadResults((prev) => ({ ...prev, [idx]: [{ type: "request", id: "—", status: 0, ok: false, error: String(err) }] }));
      setUploadState((prev) => ({ ...prev, [idx]: "error" }));
    }
  };

  const generateBatch = async () => {
    setBatchGenerating(true);
    setBatchResults([]);
    const results: BatchResult[] = [];

    for (const shell of shellTypes) {
      const shellPresets = allPresets[shell.name] ?? [];
      for (const presetSummary of shellPresets) {
        const qty = batchQuantities[presetSummary.filename] ?? 0;
        if (qty <= 0) continue;

        // Steps 1-3 happen once per preset (templates/form data are shared across instances)
        let preset: ShellPreset;
        let templateMap: Record<number, SubmodelTemplate>;
        let freshOperations: Record<string, OperationCapability>;
        let formDataMap: Record<number, FormData>;
        let assetNameVal: string;
        let assetCategoryVal: string;

        try {
          // 1. Fetch full preset data
          const presetRes = await fetch(`/api/aas-configurator/presets/${presetSummary.filename}`);
          if (!presetRes.ok) throw new Error(`Failed to fetch preset (${presetRes.status})`);
          preset = await presetRes.json() as ShellPreset;

          // 2. Load templates for every slot
          const templateResults = await Promise.all(
            shell.submodels.map((slot) =>
              slot.template_file
                ? fetch(`/api/aas-configurator/templates/${slot.template_file}`)
                    .then((r) => r.json() as Promise<SubmodelTemplate>)
                    .catch(() => null)
                : Promise.resolve(null)
            )
          );
          templateMap = {};
          freshOperations = {};
          templateResults.forEach((t, i) => {
            if (!t) return;
            templateMap[i] = t;
            if (t.operations) Object.assign(freshOperations, t.operations);
          });

          // 3. Merge preset data into form state per slot
          formDataMap = {};
          shell.submodels.forEach((slot, i) => {
            const presetSlotData = preset.submodels?.[slot.id_short] as Record<string, unknown> | undefined;
            if (presetSlotData) formDataMap[i] = mergePresetIntoForm({}, presetSlotData);
          });

          assetNameVal = preset.asset_name ?? presetSummary.label;
          // asset_type drives the {asset_type} token in the IRI pattern; fall back to asset_category
          assetCategoryVal = (preset as unknown as Record<string, unknown>).asset_type as string ?? preset.asset_category ?? "";
        } catch (err) {
          results.push({ presetFilename: presetSummary.filename, presetLabel: presetSummary.label, shellLabel: shell.label, quantity: qty, succeeded: 0, ok: false, errors: [String(err)] });
          continue;
        }

        // Steps 4-6 repeat once per instance — each gets a unique UUID
        let succeeded = 0;
        const errors: string[] = [];

        for (let n = 0; n < qty; n++) {
          try {
            const uuid = crypto.randomUUID();
            const instanceShellId = applyPattern(shell.id_pattern, assetNameVal, assetCategoryVal, uuid);
            const instanceGlobalAssetId = applyPattern(shell.global_asset_id_pattern, assetNameVal, assetCategoryVal, uuid);

            const bomSlotIdx = shell.submodels.findIndex((s) => s.id_short === "BillOfMaterials");
            const bomSubmodelId = bomSlotIdx >= 0
              ? buildSubmodelId(instanceShellId, shell.submodels[bomSlotIdx])
              : undefined;

            let capabilitySubmodelInputs: CapabilitySubmodelInput[] = [];
            const baseSubmodelInputs = shell.submodels
              .map((slot, i) => {
                const template = templateMap[i];
                if (!template) return null;
                const rawForm = formDataMap[i] ?? {};
                const derivedCtx = { AssetName: assetNameVal, AssetCategory: assetCategoryVal, ...flattenFormData(rawForm) };
                const withDerived = applyDerivedFields(template.elements, rawForm, derivedCtx);
                let formDataFinal = withDerived;
                if (slot.template_file === "sub_assembly_bop") {
                  const result = resolveBopForGeneration(withDerived, freshOperations, instanceShellId, shell.submodels.length, bomSubmodelId);
                  formDataFinal = result.bopData;
                  capabilitySubmodelInputs = result.capabilitySubmodels;
                }
                return { template_file: slot.template_file, id_short: slot.id_short, id: buildSubmodelId(instanceShellId, slot), form_data: formDataFinal };
              })
              .filter(Boolean);

            // 4. Generate
            const genRes = await fetch("/api/aas-configurator/generate", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                shell_type: shell.name,
                name: assetNameVal,
                category: assetCategoryVal,
                shell_id: instanceShellId,
                global_asset_id: instanceGlobalAssetId,
                submodels: [...baseSubmodelInputs, ...capabilitySubmodelInputs],
              }),
            });
            if (!genRes.ok) {
              const err = await genRes.json() as { error?: string };
              throw new Error(err.error ?? `Generation failed (${genRes.status})`);
            }
            const env = await genRes.json() as Record<string, unknown>;
            const shellObj = (env.assetAdministrationShells as Record<string, unknown>[])[0];
            const envSubmodels = env.submodels as Record<string, unknown>[];

            // 5. Upload to BaSyx
            const uploadRes = await fetch("/api/aas-configurator/upload", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ serverUrl: batchServerUrl, shell: shellObj, submodels: envSubmodels }),
            });
            const uploadData = await uploadRes.json() as { results: UploadResult[] };
            const firstFail = uploadData.results.find((r) => !r.ok);
            if (firstFail) throw new Error(firstFail.error ?? `Upload failed (${firstFail.status})`);

            // 6. Register in local inventory
            const assetInfo = (shellObj.assetInformation ?? {}) as Record<string, unknown>;
            await fetch("/api/inventory", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                id: shellObj.id,
                globalAssetId: (assetInfo.globalAssetId as string) ?? "",
                name: assetNameVal,
                category: assetCategoryVal,
                shellTypeName: shell.name,
                serverUrl: batchServerUrl,
              }),
            });

            succeeded++;
          } catch (err) {
            errors.push(`Instance ${n + 1}: ${String(err)}`);
          }
        }

        results.push({ presetFilename: presetSummary.filename, presetLabel: presetSummary.label, shellLabel: shell.label, quantity: qty, succeeded, ok: errors.length === 0, errors });
      }
    }

    setBatchResults(results);
    setBatchGenerating(false);
  };

  const reset = () => {
    setStep({ kind: "shell-select" });
    setSelectedShell(null);
    setSelectedPreset(null);
    setPresetApplied(false);
    setAssetName("");
    setAssetCategory("");
    setQuantity(1);
    setLoadedTemplates({});
    setSubmodelForms({});
    setFilledSlots(new Set());
    setAasInstances(null);
    setExtraSlots([]);
    setBopOperations({});
    setCapabilityTemplates({});
  };

  /* ── inline capability map: operation name → template elements ── */
  const inlineCapabilityMap: Record<string, TemplateElement[]> = {};
  Object.entries(bopOperations).forEach(([op, cap]) => {
    const tpl = capabilityTemplates[cap.template_file];
    if (tpl) inlineCapabilityMap[op] = tpl.elements;
  });

  /* ── render ── */

  return (
    <div className="min-h-screen bg-background p-6">
      <div className="max-w-3xl mx-auto">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-3">
            <Layers className="w-6 h-6 text-primary" />
            <h1 className="text-2xl font-bold">AAS Instance Configurator</h1>
          </div>
          <button
            type="button"
            onClick={() => setSettingsOpen((o) => !o)}
            className={`flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-sm transition-colors ${settingsOpen ? "border-primary text-primary bg-primary/5" : "border-border text-muted-foreground hover:text-foreground"}`}
          >
            <Settings className="w-4 h-4" /> Settings
          </button>
        </div>

        {settingsOpen && (
          <div className="mb-6 rounded-xl border border-border bg-card p-5 flex flex-col gap-3">
            <h2 className="font-semibold text-sm flex items-center gap-2">
              <FolderOpen className="w-4 h-4 text-primary" />
              Generator Path
            </h2>
            <p className="text-xs text-muted-foreground -mt-1">
              Absolute path to the <span className="font-mono">BaSyx_AAS_Generator</span> folder.
              Update this when the project moves to a new PC.
            </p>
            <div className="flex gap-2">
              <input
                type="text"
                className={inputClass()}
                value={generatorPath}
                onChange={(e) => { setGeneratorPath(e.target.value); setPathSaveState("idle"); }}
                placeholder="C:\path\to\BaSyx_AAS_Generator"
              />
              <button
                type="button"
                disabled={!generatorPath.trim() || pathSaveState === "saving"}
                onClick={saveGeneratorPath}
                className="flex items-center gap-2 rounded-lg bg-primary text-primary-foreground px-4 py-2 text-sm font-semibold disabled:opacity-40 hover:opacity-90 shrink-0"
              >
                {pathSaveState === "saving" ? <><RefreshCw className="w-3.5 h-3.5 animate-spin" /> Saving…</> : "Save"}
              </button>
            </div>
            {pathSaveState === "saved" && (
              <span className="flex items-center gap-1 text-xs text-primary"><Check className="w-3.5 h-3.5" /> Saved — shell types refreshed.</span>
            )}
            {pathSaveState === "error" && (
              <span className="text-xs text-destructive">Failed to save — check the server log.</span>
            )}
          </div>
        )}

        <p className="text-sm text-muted-foreground mb-8">
          Select a shell type, optionally load a preset, fill in each submodel,
          and export a BaSyx-compatible AAS Environment JSON.
        </p>

        <StepBar current={step} shellType={activeShell} />

        {/* ── SHELL SELECT + PRESET ── */}
        {step.kind === "shell-select" && (
          <div className="flex flex-col gap-6">
            {/* shell type selection */}
            <div className="flex flex-col gap-3">
              <h2 className="font-semibold text-lg">1. Choose a Shell Type</h2>
              <p className="text-sm text-muted-foreground -mt-1">
                Required submodels in blue, optional in grey.
              </p>
              {loadingShells ? (
                <div className="flex items-center gap-2 text-muted-foreground">
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  Loading shell types…
                </div>
              ) : (
                <div className="flex flex-col gap-3">
                  {shellTypes.map((s) => (
                    <ShellCard
                      key={s.name}
                      shell={s}
                      selected={selectedShell?.name === s.name}
                      selectedCategory={selectedShell?.name === s.name ? selectedCategory : null}
                      onClick={() => {
                        setSelectedShell(s);
                        setSelectedCategory(null);
                        setLoadedTemplates({});
                        setSubmodelForms({});
                        setFilledSlots(new Set());
                        setPresetApplied(false);
                        setSelectedPreset(null);
                      }}
                      onCategorySelect={(cat) => {
                        setSelectedCategory(cat);
                        setSelectedPreset(null);
                        setPresetApplied(false);
                        setPresetIncludes(null);
                      }}
                    />
                  ))}
                </div>
              )}
            </div>

            {/* preset selection — only shown once a shell is picked */}
            {selectedShell && (
              <div className="flex flex-col gap-3">
                <div className="flex items-center gap-2">
                  <h2 className="font-semibold text-lg">
                    2. Load a Preset{" "}
                    <span className="text-muted-foreground font-normal text-sm">
                      (optional)
                    </span>
                  </h2>
                  {presetApplied && (
                    <span className="flex items-center gap-1 text-xs text-primary bg-primary/10 rounded-full px-2 py-0.5">
                      <Check className="w-3 h-3" /> Applied
                    </span>
                  )}
                </div>
                <p className="text-sm text-muted-foreground -mt-1">
                  Presets pre-fill common values — you still edit anything you
                  need to change.
                </p>

                {selectedShell.categories.length > 0 && !selectedCategory ? (
                  <div className="rounded-lg border border-dashed border-border p-4 text-sm text-muted-foreground">
                    Select a category above to see available presets.
                  </div>
                ) : loadingPresets ? (
                  <div className="flex items-center gap-2 text-muted-foreground">
                    <RefreshCw className="w-4 h-4 animate-spin" />
                    Loading presets…
                  </div>
                ) : presets.length === 0 ? (
                  <div className="rounded-lg border border-dashed border-border p-4 text-sm text-muted-foreground flex items-center gap-2">
                    <PlusCircle className="w-4 h-4 shrink-0" />
                    No presets for this category yet.
                  </div>
                ) : (
                  <div className="flex flex-col gap-2">
                    {presets.map((p) => (
                      <PresetCard
                        key={p.filename}
                        preset={p}
                        selected={selectedPreset?.filename === p.filename}
                        onClick={async () => {
                          setSelectedPreset(p);
                          await applyPreset(p);
                        }}
                      />
                    ))}
                    {presetApplied && (
                      <button
                        type="button"
                        onClick={() => {
                          setSelectedPreset(null);
                          setPresetApplied(false);
                          setSubmodelForms({});
                          setAssetName("");
                          setAssetCategory("");
                          setPresetIncludes(null);
                        }}
                        className="text-xs text-muted-foreground hover:text-foreground underline w-fit"
                      >
                        Clear preset and start blank
                      </button>
                    )}
                  </div>
                )}
              </div>
            )}

            <div className="flex flex-col gap-2">
              <label className="text-sm font-semibold">Quantity</label>
              <div className="flex items-center gap-3">
                <input
                  type="number"
                  min={1}
                  max={500}
                  className="w-28 rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                  value={quantity}
                  onChange={(e) => setQuantity(Math.max(1, parseInt(e.target.value) || 1))}
                />
                <span className="text-xs text-muted-foreground">
                  {quantity === 1 ? "1 instance" : `${quantity} instances`} — each gets a unique UUID
                </span>
              </div>
            </div>

            <div className="flex justify-end gap-3">
              {presetApplied ? (
                <>
                  <button
                    type="button"
                    onClick={goNext}
                    className="flex items-center gap-2 rounded-lg border border-border bg-background px-6 py-2.5 text-sm font-semibold hover:bg-muted"
                  >
                    Edit before creating <ChevronRight className="w-4 h-4" />
                  </button>
                  <button
                    type="button"
                    onClick={createWithPreset}
                    className="flex items-center gap-2 rounded-lg bg-primary text-primary-foreground px-6 py-2.5 text-sm font-semibold hover:opacity-90"
                  >
                    <Check className="w-4 h-4" /> Create with preset
                  </button>
                </>
              ) : (
                <button
                  type="button"
                  disabled={!selectedShell}
                  onClick={goNext}
                  className="flex items-center gap-2 rounded-lg bg-primary text-primary-foreground px-6 py-2.5 text-sm font-semibold disabled:opacity-40 hover:opacity-90"
                >
                  Continue from scratch <ChevronRight className="w-4 h-4" />
                </button>
              )}
            </div>
          </div>
        )}

        {/* ── INSTANCE INFO ── */}
        {step.kind === "instance-info" && selectedShell && (
          <div className="flex flex-col gap-6">
            <div>
              <h2 className="font-semibold text-lg">Instance Information</h2>
              <p className="text-sm text-muted-foreground mt-1">
                The IDs are generated from the shell template's pattern. The
                name and category are the only free variables.
              </p>
            </div>

            <div className="flex flex-col gap-4 bg-card border border-border rounded-xl p-6">
              <div className="grid grid-cols-2 gap-4">
                <div className="flex flex-col gap-1">
                  <label className="text-sm font-medium">Asset Name</label>
                  <input
                    type="text"
                    placeholder="e.g. FuseBox_A1"
                    className={inputClass()}
                    value={assetName}
                    onChange={(e) => setAssetName(e.target.value)}
                  />
                </div>
                <div className="flex flex-col gap-1">
                  <label className="text-sm font-medium">Category</label>
                  <input
                    type="text"
                    placeholder="e.g. Electrical"
                    className={inputClass()}
                    value={assetCategory}
                    onChange={(e) => setAssetCategory(e.target.value)}
                  />
                </div>
              </div>

              <div className="flex flex-col gap-1">
                <label className="text-sm font-medium text-muted-foreground">
                  Shell ID (generated)
                </label>
                <div className="rounded-md bg-muted border border-border px-3 py-2 text-xs font-mono break-all text-muted-foreground">
                  {shellId}
                </div>
              </div>

              <div className="flex flex-col gap-1">
                <label className="text-sm font-medium text-muted-foreground">
                  Global Asset ID (generated)
                </label>
                <div className="rounded-md bg-muted border border-border px-3 py-2 text-xs font-mono break-all text-muted-foreground">
                  {globalAssetId}
                </div>
              </div>

              {presetApplied && selectedPreset && (
                <div className="flex items-center gap-2 rounded-md bg-primary/5 border border-primary/20 px-3 py-2 text-xs text-primary">
                  <Sparkles className="w-3.5 h-3.5 shrink-0" />
                  Preset &quot;{selectedPreset.label}&quot; applied — form
                  fields are pre-filled. Edit anything you need to change.
                </div>
              )}
            </div>

            <div className="flex justify-between">
              <button
                type="button"
                onClick={goBack}
                className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground"
              >
                <ArrowLeft className="w-4 h-4" /> Back
              </button>
              <button
                type="button"
                disabled={!assetName}
                onClick={goNext}
                className="flex items-center gap-2 rounded-lg bg-primary text-primary-foreground px-6 py-2.5 text-sm font-semibold disabled:opacity-40 hover:opacity-90"
              >
                {loadingTemplate ? (
                  <>
                    <RefreshCw className="w-4 h-4 animate-spin" /> Loading…
                  </>
                ) : (
                  <>
                    Start filling submodels <ArrowRight className="w-4 h-4" />
                  </>
                )}
              </button>
            </div>
          </div>
        )}

        {/* ── SUBMODEL FORM ── */}
        {step.kind === "submodel" && activeShell && currentSlot && (
          <div className="flex flex-col gap-6">
            <div>
              <div className="flex items-center gap-2 mb-1">
                <span className="text-xs text-muted-foreground font-mono">
                  Submodel {currentIndex + 1} of{" "}
                  {activeShell.submodels.length}
                </span>
                {!currentSlot.required && (
                  <span className="text-xs rounded-full bg-muted px-2 py-0.5 text-muted-foreground">
                    optional
                  </span>
                )}
                {presetApplied && (
                  <span className="flex items-center gap-1 text-xs text-primary">
                    <Sparkles className="w-3 h-3" /> preset applied
                  </span>
                )}
              </div>
              <h2 className="font-semibold text-lg">{currentSlot.id_short}</h2>
              <p className="text-sm text-muted-foreground mt-1">
                {currentTemplate?.description ?? currentSlot.description}
              </p>
            </div>

            <SubmodelProgress
              slots={activeShell.submodels}
              currentIndex={currentIndex}
              filledSlots={filledSlots}
            />

            {loadingTemplate ? (
              <div className="flex items-center gap-2 text-muted-foreground py-8">
                <RefreshCw className="w-4 h-4 animate-spin" />
                Loading template…
              </div>
            ) : !currentSlot.template_file ? (
              <div className="rounded-lg border border-amber-300 bg-amber-50 dark:bg-amber-950/20 p-4 text-sm text-amber-700 dark:text-amber-400">
                No submodel template linked to{" "}
                <span className="font-mono">{currentSlot.template_id}</span>.
                Check that the submodel template&apos;s <code>id</code> field
                matches this URI.
              </div>
            ) : currentTemplate ? (
              <div className="flex flex-col gap-4">
                {(presetIncludes?.[currentSlot.id_short]
                  ? currentTemplate.elements.filter(el =>
                      presetIncludes![currentSlot.id_short].includes(el.id_short)
                    )
                  : currentTemplate.elements
                ).map((el) => (
                  <FieldRenderer
                    key={el.id_short}
                    element={el}
                    value={currentFormData[el.id_short] as FormValue}
                    onChange={(v) => updateCurrentField(el.id_short, v)}
                    path={`slot-${currentIndex}`}
                    context={{
                      AssetName: assetName,
                      AssetCategory: assetCategory,
                      ...flattenFormData(currentFormData),
                    }}
                    inlineCapabilityMap={inlineCapabilityMap}
                    bomEntries={bomEntries}
                    processStepEntries={processStepEntries}
                  />
                ))}
              </div>
            ) : (
              <p className="text-sm text-destructive">
                Failed to load template &quot;{currentSlot.template_file}&quot;.
              </p>
            )}

            <div className="flex justify-between mt-4">
              <button
                type="button"
                onClick={goBack}
                className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground"
              >
                <ArrowLeft className="w-4 h-4" /> Back
              </button>
              <button
                type="button"
                disabled={loadingTemplate || generating}
                onClick={goNext}
                className="flex items-center gap-2 rounded-lg bg-primary text-primary-foreground px-6 py-2.5 text-sm font-semibold disabled:opacity-40 hover:opacity-90"
              >
                {currentIndex + 1 < activeShell.submodels.length ? (
                  <>
                    Next submodel <ArrowRight className="w-4 h-4" />
                  </>
                ) : generating ? (
                  <>
                    <RefreshCw className="w-4 h-4 animate-spin" /> Generating…
                  </>
                ) : (
                  <>
                    Generate AAS <Check className="w-4 h-4" />
                  </>
                )}
              </button>
            </div>
          </div>
        )}

        {/* ── REVIEW & EXPORT ── */}
        {step.kind === "review" && activeShell && (aasInstances || generateError) && (
          <div className="flex flex-col gap-6">
            {generateError && (
              <div className="flex items-start gap-2 rounded-lg border border-destructive/40 bg-destructive/10 p-4 text-sm text-destructive">
                <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                <div>
                  <span className="font-semibold">Generation failed</span>
                  <pre className="mt-1 text-xs whitespace-pre-wrap break-all font-mono">{generateError}</pre>
                </div>
              </div>
            )}
            {aasInstances && (<>
            <div className="flex items-start justify-between">
              <div>
                <h2 className="font-semibold text-lg">
                  Generated AAS Environment
                </h2>
                <p className="text-sm text-muted-foreground mt-1">
                  Download the shell and each submodel as individual files — one upload per file into BaSyx.
                </p>
              </div>
              <button
                type="button"
                onClick={reset}
                className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground border border-border rounded-md px-3 py-1.5 shrink-0"
              >
                <RefreshCw className="w-3 h-3" /> Start over
              </button>
            </div>

            <div className="flex gap-2 items-center rounded-xl border border-border bg-card p-4">
              <Upload className="w-4 h-4 text-muted-foreground shrink-0" />
              <input
                type="text"
                className={inputClass()}
                value={serverUrl}
                onChange={(e) => { setServerUrl(e.target.value); setUploadState({}); setUploadResults({}); }}
                placeholder="http://localhost:8081"
              />
              <button
                type="button"
                disabled={!serverUrl.trim() || aasInstances.some((_, i) => (uploadState[i] ?? "idle") === "uploading")}
                onClick={() => aasInstances.forEach((env, i) => uploadToBaSyx(env, i))}
                className="flex items-center gap-2 rounded-lg bg-primary text-primary-foreground px-4 py-2 text-sm font-semibold disabled:opacity-40 hover:opacity-90 shrink-0"
              >
                <Upload className="w-3.5 h-3.5" /> Upload All
              </button>
            </div>

            <div className="grid grid-cols-2 gap-3 text-sm">
              <div className="bg-card border border-border rounded-lg p-3 flex flex-col gap-1">
                <span className="text-xs text-muted-foreground">Shell type</span>
                <span className="font-medium">{activeShell.label}</span>
              </div>
              <div className="bg-card border border-border rounded-lg p-3 flex flex-col gap-1">
                <span className="text-xs text-muted-foreground">Instances</span>
                <span className="font-medium">{aasInstances.length}</span>
              </div>
              <div className="bg-card border border-border rounded-lg p-3 flex flex-col gap-1">
                <span className="text-xs text-muted-foreground">Submodels per instance</span>
                <span className="font-medium">
                  {(aasInstances[0]?.submodels as unknown[] ?? []).length}
                </span>
              </div>
              {selectedPreset && (
                <div className="col-span-2 bg-primary/5 border border-primary/20 rounded-lg p-3 flex items-center gap-2 text-xs text-primary">
                  <Sparkles className="w-3.5 h-3.5 shrink-0" />
                  Based on preset: <strong>{selectedPreset.label}</strong>
                </div>
              )}
            </div>

            {/* per-instance: shell + individual submodels */}
            {aasInstances.map((env, idx) => {
              const shell = (env.assetAdministrationShells as Record<string, unknown>[])[0];
              const submodels = env.submodels as Record<string, unknown>[];
              const label = aasInstances.length === 1
                ? activeShell.name
                : `${activeShell.name}_${idx + 1}`;
              const iState = uploadState[idx] ?? "idle";
              const iResults = uploadResults[idx] ?? [];
              return (
                <div key={idx} className="flex flex-col gap-3 rounded-xl border border-border p-4">
                  {aasInstances.length > 1 && (
                    <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                      Instance {idx + 1}
                    </span>
                  )}
                  <JsonOutput label={`${label}_shell`} data={shell} />
                  {submodels.map((sm, si) => (
                    <JsonOutput
                      key={si}
                      label={`${label}_${(sm.idShort as string) ?? activeShell.submodels[si]?.id_short ?? `submodel_${si + 1}`}`}
                      data={sm}
                    />
                  ))}
                  <div className="flex flex-col gap-1.5 pt-1 border-t border-border">
                    <button
                      type="button"
                      disabled={iState === "uploading" || !serverUrl.trim()}
                      onClick={() => uploadToBaSyx(env, idx)}
                      className="flex items-center gap-2 rounded-lg bg-primary text-primary-foreground px-4 py-2 text-sm font-semibold disabled:opacity-40 hover:opacity-90 w-fit"
                    >
                      {iState === "uploading" ? (
                        <><RefreshCw className="w-3.5 h-3.5 animate-spin" /> Uploading…</>
                      ) : (
                        <><Upload className="w-3.5 h-3.5" /> Upload to BaSyx</>
                      )}
                    </button>
                    {iResults.map((r, i) => (
                      <div key={i} className={`flex items-start gap-2 rounded-md px-3 py-2 text-xs ${r.ok ? "bg-green-50 dark:bg-green-950/20 text-green-700 dark:text-green-400" : "bg-destructive/10 text-destructive"}`}>
                        {r.ok ? <Check className="w-3.5 h-3.5 shrink-0 mt-0.5" /> : <AlertCircle className="w-3.5 h-3.5 shrink-0 mt-0.5" />}
                        <span className="font-mono font-semibold shrink-0">{r.type}</span>
                        <span className="truncate text-muted-foreground flex-1">{r.id}</span>
                        <span className="shrink-0">{r.ok ? `${r.status} OK` : `${r.status || "ERR"} — ${r.error ?? "failed"}`}</span>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}

            {/* ── SAVE AS PRESET ── */}
            <div className="flex flex-col gap-3 rounded-xl border border-border bg-card p-5">
              <h3 className="font-semibold text-sm flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-primary" />
                Save as Preset
              </h3>
              <p className="text-xs text-muted-foreground -mt-1">
                Save this configuration as a reusable preset. All filled-in collections and properties will be included.
              </p>
              <div className="flex flex-col gap-3">
                <div className="flex flex-col gap-1">
                  <label className="text-sm font-medium">Preset Name</label>
                  <input
                    type="text"
                    placeholder="e.g. Fuse Module – Standard Assembly"
                    className={inputClass()}
                    value={presetSaveLabel}
                    onChange={(e) => { setPresetSaveLabel(e.target.value); setPresetSaveState("idle"); }}
                  />
                </div>
                <div className="flex flex-col gap-1">
                  <label className="text-sm font-medium">Description <span className="text-muted-foreground font-normal">(optional)</span></label>
                  <input
                    type="text"
                    placeholder="Short description of this preset"
                    className={inputClass()}
                    value={presetSaveDesc}
                    onChange={(e) => { setPresetSaveDesc(e.target.value); setPresetSaveState("idle"); }}
                  />
                </div>
                <div className="flex items-center gap-3">
                  <button
                    type="button"
                    disabled={!presetSaveLabel.trim() || presetSaveState === "saving"}
                    onClick={saveAsPreset}
                    className="flex items-center gap-2 rounded-lg bg-primary text-primary-foreground px-4 py-2 text-sm font-semibold disabled:opacity-40 hover:opacity-90"
                  >
                    {presetSaveState === "saving" ? (
                      <><RefreshCw className="w-3.5 h-3.5 animate-spin" /> Saving…</>
                    ) : (
                      <><Sparkles className="w-3.5 h-3.5" /> Save Preset</>
                    )}
                  </button>
                  {presetSaveState === "saved" && (
                    <span className="flex items-center gap-1 text-xs text-primary">
                      <Check className="w-3.5 h-3.5" /> Saved to shell_presets/
                    </span>
                  )}
                  {presetSaveState === "error" && (
                    <span className="text-xs text-destructive">Failed to save — check the server log.</span>
                  )}
                </div>
              </div>
            </div>

            <div className="flex justify-between mt-2">
              <button
                type="button"
                onClick={goBack}
                className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground"
              >
                <ArrowLeft className="w-4 h-4" /> Back to last submodel
              </button>
              <button
                type="button"
                onClick={reset}
                className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground"
              >
                <RefreshCw className="w-3.5 h-3.5" /> Start over
              </button>
            </div>
            </>)}
          </div>
        )}
        {/* ── BATCH / SHOPPING LIST ── */}
        <div className="mt-10 pt-8 border-t border-border">
          <button
            type="button"
            onClick={() => setBatchOpen((o) => !o)}
            className="flex items-center gap-2 w-full text-left"
          >
            <ShoppingCart className="w-5 h-5 text-primary" />
            <span className="font-semibold text-base flex-1">Test Batch Generator</span>
            <span className="text-xs text-muted-foreground mr-2 hidden sm:block">
              Generate &amp; upload a full set of presets in one click
            </span>
            {batchOpen
              ? <ChevronDown className="w-4 h-4 text-muted-foreground" />
              : <ChevronRight className="w-4 h-4 text-muted-foreground" />}
          </button>

          {batchOpen && (
            <div className="mt-4 flex flex-col gap-5">
              {/* Server URL */}
              <div className="flex gap-2 items-center rounded-xl border border-border bg-card p-4">
                <Upload className="w-4 h-4 text-muted-foreground shrink-0" />
                <input
                  type="text"
                  className={inputClass()}
                  value={batchServerUrl}
                  onChange={(e) => { setBatchServerUrl(e.target.value); setBatchResults([]); }}
                  placeholder="http://localhost:8081"
                />
              </div>

              {/* Preset checklist */}
              {allPresetsLoading ? (
                <div className="flex items-center gap-2 text-muted-foreground text-sm">
                  <RefreshCw className="w-4 h-4 animate-spin" /> Loading presets…
                </div>
              ) : Object.keys(allPresets).length === 0 ? (
                <div className="rounded-lg border border-dashed border-border p-4 text-sm text-muted-foreground">
                  No presets found. Add YAML files to <span className="font-mono">shell_presets/</span> to get started.
                </div>
              ) : (() => {
                const totalInstances = Object.values(batchQuantities).reduce((s, q) => s + Math.max(0, q), 0);
                const selectedCount = Object.values(batchQuantities).filter((q) => q > 0).length;
                return (
                  <div className="flex flex-col gap-4">
                    <div className="flex gap-3 items-center">
                      <button
                        type="button"
                        onClick={() => setBatchQuantities(Object.fromEntries(Object.values(allPresets).flat().map((p) => [p.filename, 1])))}
                        className="text-xs text-primary underline"
                      >
                        Select all
                      </button>
                      <button
                        type="button"
                        onClick={() => setBatchQuantities({})}
                        className="text-xs text-muted-foreground underline"
                      >
                        Deselect all
                      </button>
                      <span className="text-xs text-muted-foreground ml-auto">
                        {selectedCount} preset{selectedCount !== 1 ? "s" : ""} — {totalInstances} instance{totalInstances !== 1 ? "s" : ""}
                      </span>
                    </div>

                    {Object.entries(allPresets).map(([shellName, presets]) => {
                      const shellDef = shellTypes.find((s) => s.name === shellName);
                      return (
                        <div key={shellName} className="flex flex-col gap-2">
                          <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                            {shellDef?.label ?? shellName}
                          </span>
                          {presets.map((p) => {
                            const qty = batchQuantities[p.filename] ?? 0;
                            const checked = qty > 0;
                            return (
                              <div
                                key={p.filename}
                                className="flex items-center gap-3 rounded-lg border border-border p-3 hover:bg-muted/30 transition-colors"
                              >
                                <input
                                  type="checkbox"
                                  id={`batch-${p.filename}`}
                                  className="shrink-0 accent-primary cursor-pointer"
                                  checked={checked}
                                  onChange={(e) =>
                                    setBatchQuantities((prev) => ({
                                      ...prev,
                                      [p.filename]: e.target.checked ? 1 : 0,
                                    }))
                                  }
                                />
                                <label htmlFor={`batch-${p.filename}`} className="flex flex-col gap-0.5 min-w-0 flex-1 cursor-pointer">
                                  <span className="text-sm font-medium">{p.label}</span>
                                  {p.description && (
                                    <span className="text-xs text-muted-foreground">{p.description}</span>
                                  )}
                                  <div className="flex gap-1.5 mt-0.5 flex-wrap">
                                    {p.asset_name && (
                                      <span className="text-xs font-mono bg-muted rounded px-1.5 py-0.5 text-muted-foreground">
                                        {p.asset_name}
                                      </span>
                                    )}
                                    {p.asset_category && (
                                      <span className="text-xs bg-muted rounded px-1.5 py-0.5 text-muted-foreground">
                                        {p.asset_category}
                                      </span>
                                    )}
                                  </div>
                                </label>
                                {checked && (
                                  <input
                                    type="number"
                                    min={1}
                                    max={99}
                                    value={qty}
                                    onChange={(e) =>
                                      setBatchQuantities((prev) => ({
                                        ...prev,
                                        [p.filename]: Math.max(1, parseInt(e.target.value) || 1),
                                      }))
                                    }
                                    className="w-16 rounded-md border border-border bg-background px-2 py-1 text-sm text-center focus:outline-none focus:ring-2 focus:ring-primary shrink-0"
                                  />
                                )}
                              </div>
                            );
                          })}
                        </div>
                      );
                    })}
                  </div>
                );
              })()}

              {/* Generate button + result summary */}
              {(() => {
                const totalInstances = Object.values(batchQuantities).reduce((s, q) => s + Math.max(0, q), 0);
                return (
                  <div className="flex items-center gap-3 flex-wrap">
                    <button
                      type="button"
                      disabled={totalInstances === 0 || batchGenerating || !batchServerUrl.trim()}
                      onClick={generateBatch}
                      className="flex items-center gap-2 rounded-lg bg-primary text-primary-foreground px-5 py-2.5 text-sm font-semibold disabled:opacity-40 hover:opacity-90"
                    >
                      {batchGenerating ? (
                        <><RefreshCw className="w-4 h-4 animate-spin" /> Generating…</>
                      ) : (
                        <><PackagePlus className="w-4 h-4" /> Generate &amp; Upload ({totalInstances} instance{totalInstances !== 1 ? "s" : ""})</>
                      )}
                    </button>
                    {batchResults.length > 0 && !batchGenerating && (
                      <span className="text-xs text-muted-foreground">
                        {batchResults.reduce((s, r) => s + r.succeeded, 0)}/{batchResults.reduce((s, r) => s + r.quantity, 0)} instances uploaded
                      </span>
                    )}
                  </div>
                );
              })()}

              {/* Per-preset results */}
              {batchResults.length > 0 && (
                <div className="flex flex-col gap-1.5">
                  {batchResults.map((r, i) => (
                    <div
                      key={i}
                      className={`flex flex-col gap-1 rounded-md px-3 py-2 text-xs ${
                        r.ok
                          ? "bg-green-50 dark:bg-green-950/20 text-green-700 dark:text-green-400"
                          : "bg-destructive/10 text-destructive"
                      }`}
                    >
                      <div className="flex items-center gap-2">
                        {r.ok
                          ? <Check className="w-3.5 h-3.5 shrink-0" />
                          : <AlertCircle className="w-3.5 h-3.5 shrink-0" />}
                        <span className="font-medium shrink-0">{r.presetLabel}</span>
                        <span className="text-muted-foreground shrink-0">({r.shellLabel})</span>
                        <span className="shrink-0">
                          → {r.succeeded}/{r.quantity} instance{r.quantity !== 1 ? "s" : ""} uploaded
                        </span>
                      </div>
                      {r.errors.map((e, ei) => (
                        <span key={ei} className="pl-5 break-all opacity-80">{e}</span>
                      ))}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

      </div>
    </div>
  );
}
