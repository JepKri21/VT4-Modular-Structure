import { NextResponse } from "next/server";
import fs from "fs";
import path from "path";
import yaml from "js-yaml";

import { getGeneratorPath } from "@/lib/aas-config";

type OptionsMap = Record<string, string[]>;
type DerivedMap = Record<string, string>;
type OperationsMap = Record<string, { id_short: string; template_file: string; template_id: string }>;

interface FieldOptionsFile {
  global?: OptionsMap;
  derived?: Record<string, DerivedMap>;
  operations?: OperationsMap;
  [templateName: string]: OptionsMap | Record<string, DerivedMap> | OperationsMap | undefined;
}

function loadFieldOptions(optionsFile: string, templateName: string): { options: OptionsMap; derived: DerivedMap; operations: OperationsMap } {
  try {
    const raw = fs.readFileSync(optionsFile, "utf-8");
    const doc = yaml.load(raw) as FieldOptionsFile;

    const globalOpts = (doc.global ?? {}) as OptionsMap;
    const templateOpts = (doc[templateName] ?? {}) as OptionsMap;
    const options: OptionsMap = { ...globalOpts, ...templateOpts };

    const derived: DerivedMap = (doc.derived?.[templateName] ?? {}) as DerivedMap;
    const operations: OperationsMap = (doc.operations ?? {}) as OperationsMap;

    return { options, derived, operations };
  } catch {
    return { options: {}, derived: {}, operations: {} };
  }
}

type Element = Record<string, unknown>;

function injectFieldMeta(elements: Element[], options: OptionsMap, derived: DerivedMap): Element[] {
  return elements.map((el) => {
    const result: Element = { ...el };
    const id = result.id_short as string;

    if (result.type === "property") {
      if (options[id]) result.options = options[id];
      if (derived[id]) result.derived = derived[id];
    }

    if (Array.isArray(result.elements)) {
      result.elements = injectFieldMeta(result.elements as Element[], options, derived);
    }
    return result;
  });
}

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ name: string }> }
) {
  const generatorPath = getGeneratorPath();
  const TEMPLATES_DIR = path.join(generatorPath, "submodel_templates");
  const OPTIONS_FILE = path.join(generatorPath, "field_options.yaml");
  const { name } = await params;
  const candidates = [`${name}.yaml`, `${name}.yml`];

  for (const candidate of candidates) {
    const filePath = path.join(TEMPLATES_DIR, candidate);
    if (fs.existsSync(filePath)) {
      const raw = fs.readFileSync(filePath, "utf-8");
      const doc = yaml.load(raw) as Record<string, unknown>;
      const { options, derived, operations } = loadFieldOptions(OPTIONS_FILE, name);
      const operationKeys = Object.keys(operations);
      if (operationKeys.length > 0) options["Operation"] = operationKeys;
      if (Array.isArray(doc.elements)) {
        doc.elements = injectFieldMeta(doc.elements as Element[], options, derived);
      }
      if (operationKeys.length > 0) {
        doc.operations = operations;
      }
      return NextResponse.json(doc);
    }
  }

  return NextResponse.json({ error: "Template not found" }, { status: 404 });
}
