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
  let cfg: Record<string, unknown> = {};
  try { cfg = JSON.parse(fs.readFileSync(CONFIG_FILE, "utf-8")); } catch { /* new file */ }
  cfg.generatorPath = p;
  fs.writeFileSync(CONFIG_FILE, JSON.stringify(cfg, null, 2), "utf-8");
}

export function getResourceRunnerConfig(): { runnerPath: string; pythonExe: string } {
  const envPath = (process.env.RESOURCE_RUNNER_PATH ?? "").trim();
  const envPy = (process.env.PYTHON_EXECUTABLE ?? "").trim();
  try {
    const cfg = JSON.parse(fs.readFileSync(CONFIG_FILE, "utf-8")) as {
      resourceRunnerPath?: string;
      pythonExecutable?: string;
    };
    return {
      runnerPath: envPath || cfg.resourceRunnerPath?.trim() || "",
      pythonExe: envPy || cfg.pythonExecutable?.trim() || "python",
    };
  } catch {
    return { runnerPath: envPath, pythonExe: envPy || "python" };
  }
}

export function saveResourceRunnerConfig(runnerPath: string, pythonExe: string): void {
  let cfg: Record<string, unknown> = {};
  try { cfg = JSON.parse(fs.readFileSync(CONFIG_FILE, "utf-8")); } catch { /* new file */ }
  cfg.resourceRunnerPath = runnerPath;
  cfg.pythonExecutable = pythonExe || "python";
  fs.writeFileSync(CONFIG_FILE, JSON.stringify(cfg, null, 2), "utf-8");
}
