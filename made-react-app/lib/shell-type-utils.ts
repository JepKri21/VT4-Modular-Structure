import fs from "fs";
import path from "path";
import yaml from "js-yaml";
import { getGeneratorPath } from "@/lib/aas-config";

function deepMerge(
  base: Record<string, unknown>,
  override: Record<string, unknown>
): Record<string, unknown> {
  const result: Record<string, unknown> = { ...base };
  for (const [key, val] of Object.entries(override)) {
    if (
      key in result &&
      typeof result[key] === "object" && !Array.isArray(result[key]) && result[key] !== null &&
      typeof val === "object" && !Array.isArray(val) && val !== null
    ) {
      result[key] = deepMerge(
        result[key] as Record<string, unknown>,
        val as Record<string, unknown>
      );
    } else {
      result[key] = val;
    }
  }
  return result;
}

function resolvePattern(pattern: string, ctx: Record<string, unknown>): string {
  let result = pattern.replace(/\{(\w+)\}/g, (_, key) => String(ctx[key] ?? ""));
  result = result.replace(/[-_\s]{2,}/g, (m) => m[0]);
  return result.replace(/^[-_ ]+|[-_ ]+$/g, "");
}

function isLangMap(val: unknown): val is Record<string, string> {
  return (
    typeof val === "object" && val !== null && !Array.isArray(val) &&
    Object.keys(val as object).every((k) => k.length === 2)
  );
}

function applyDerived(
  target: Record<string, unknown>,
  derived: Record<string, unknown>,
  ctx: Record<string, unknown>
): void {
  for (const [key, val] of Object.entries(derived)) {
    if (isLangMap(val)) {
      target[key] = Object.entries(val).map(([lang, pattern]) => ({
        language: lang,
        text: resolvePattern(pattern, ctx),
      }));
    } else if (typeof val === "object" && val !== null && !Array.isArray(val)) {
      const child = (target[key] as Record<string, unknown>) ?? {};
      applyDerived(child, val as Record<string, unknown>, ctx);
      target[key] = child;
    } else if (typeof val === "string") {
      target[key] = resolvePattern(val, ctx);
    }
  }
}

export function resolvePresetType(doc: Record<string, unknown>): Record<string, unknown> {
  const typeName = doc.type as string | undefined;
  if (!typeName) return doc;
  const typePath = path.join(getGeneratorPath(), "shell_templates", `${typeName}.yaml`);
  const raw = fs.readFileSync(typePath, "utf-8");
  const typeShell = yaml.load(raw) as Record<string, unknown>;
  const { type: _, ...rest } = doc;
  const merged = deepMerge(typeShell, rest);
  merged.shell = typeShell.shell;
  const derived = typeShell.derived as Record<string, unknown> | undefined;
  if (derived) {
    const matProps =
      ((merged.submodels as Record<string, unknown>)?.Properties as Record<string, unknown>)
        ?.MaterialProperties as Record<string, unknown> ?? {};
    const submodels = (merged.submodels as Record<string, unknown>) ?? {};
    applyDerived(submodels, derived, matProps);
    merged.submodels = submodels;
  }
  delete merged.derived;
  return merged;
}
