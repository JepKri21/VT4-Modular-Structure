import { NextResponse } from "next/server";
import fs from "fs";
import path from "path";
import yaml from "js-yaml";
import { getGeneratorPath } from "@/lib/aas-config";

export async function GET() {
  const TEMPLATES_DIR = path.join(getGeneratorPath(), "submodel_templates");
  try {
    const files = fs
      .readdirSync(TEMPLATES_DIR)
      .filter((f) => f.endsWith(".yaml") || f.endsWith(".yml"));

    const templates = files.map((file) => {
      const raw = fs.readFileSync(path.join(TEMPLATES_DIR, file), "utf-8");
      const doc = yaml.load(raw) as Record<string, unknown>;
      return {
        filename: file,
        name: path.basename(file, path.extname(file)),
        id_short: doc.id_short ?? path.basename(file, path.extname(file)),
        id: doc.id ?? "",
        description: doc.description ?? "",
      };
    });

    return NextResponse.json(templates);
  } catch (err) {
    return NextResponse.json(
      { error: String(err) },
      { status: 500 }
    );
  }
}
