import fs from "fs";
import path from "path";

const CONFIG_FILE = path.join(process.cwd(), "aas-config.json");

const DEFAULT_PATH = path.join(
  process.cwd(),
  "..",
  "Implementation2.0",
  "ClassesAndBuilderMethods",
  "BaSyx_AAS_Generator"
);

export function getGeneratorPath(): string {
  try {
    const raw = fs.readFileSync(CONFIG_FILE, "utf-8");
    const cfg = JSON.parse(raw) as { generatorPath?: string };
    if (cfg.generatorPath?.trim()) return cfg.generatorPath.trim();
  } catch {
    // fall through to default
  }
  return DEFAULT_PATH;
}

export function saveGeneratorPath(p: string): void {
  fs.writeFileSync(CONFIG_FILE, JSON.stringify({ generatorPath: p }, null, 2), "utf-8");
}
