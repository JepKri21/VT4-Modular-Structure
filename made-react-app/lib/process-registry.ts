import { ChildProcess, spawn } from "child_process";
import path from "path";
import fs from "fs";
import os from "os";
import crypto from "crypto";
import { pool } from "@/lib/db";
import { CREATE_RESOURCE_PROCESSES_TABLE_SQL } from "@/lib/inventory";
import { getResourceRunnerConfig, getLineControllerConfig, getMesApiConfig } from "@/lib/aas-config";

// Module-level singleton — one instance per Next.js server process
const registry = new Map<string, ChildProcess>();

const LOG_MAX_LINES = 200;
const LOG_DIR = path.join(os.tmpdir(), "resource-runner-logs");

function ensureLogDir(): void {
  if (!fs.existsSync(LOG_DIR)) fs.mkdirSync(LOG_DIR, { recursive: true });
}

function logFilePath(shellId: string): string {
  const hash = crypto.createHash("sha1").update(shellId).digest("hex").slice(0, 16);
  return path.join(LOG_DIR, `${hash}.log`);
}

function appendLog(shellId: string, chunk: Buffer | string): void {
  ensureLogDir();
  const text = chunk.toString("utf-8");
  fs.appendFileSync(logFilePath(shellId), text, "utf-8");
}

export function getProcessLogs(shellId: string): string[] {
  const file = logFilePath(shellId);
  if (!fs.existsSync(file)) return [];
  const content = fs.readFileSync(file, "utf-8");
  const lines = content.split(/\r?\n/).filter((l) => l.length > 0);
  // Return only the last LOG_MAX_LINES lines
  return lines.slice(-LOG_MAX_LINES);
}

export function clearProcessLogs(shellId: string): void {
  const file = logFilePath(shellId);
  if (fs.existsSync(file)) fs.unlinkSync(file);
}

async function ensureTable(): Promise<void> {
  await pool.query(CREATE_RESOURCE_PROCESSES_TABLE_SQL);
}

function isPidAlive(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

export async function getLiveShellIds(): Promise<Set<string>> {
  await ensureTable();
  const live = new Set<string>();

  // In-memory handles are authoritative
  for (const [shellId, child] of Array.from(registry.entries())) {
    if (child.exitCode === null && child.signalCode === null) {
      live.add(shellId);
    } else {
      registry.delete(shellId);
      await pool.query("DELETE FROM resource_processes WHERE shell_id = $1", [shellId]).catch(() => {});
    }
  }

  // Check DB for PIDs not in registry (post-server-restart scenario)
  const rows = await pool.query("SELECT shell_id, pid FROM resource_processes");
  for (const row of rows.rows as { shell_id: string; pid: number }[]) {
    if (registry.has(row.shell_id)) continue;
    if (isPidAlive(row.pid)) {
      live.add(row.shell_id);
    } else {
      await pool.query("DELETE FROM resource_processes WHERE shell_id = $1", [row.shell_id]).catch(() => {});
    }
  }

  return live;
}

export interface StartResult {
  ok: boolean;
  pid?: number;
  error?: string;
}

export async function startRunner(shellId: string, serverUrl: string): Promise<StartResult> {
  await ensureTable();

  const existing = registry.get(shellId);
  if (existing && existing.exitCode === null && existing.signalCode === null) {
    return { ok: false, error: "Already running" };
  }
  if (existing) registry.delete(shellId);

  const { runnerPath, pythonExe } = getResourceRunnerConfig();
  if (!runnerPath) {
    return { ok: false, error: "Resource runner path not configured. Set it in the Resource Control settings." };
  }

  // Clear log file from previous run
  clearProcessLogs(shellId);

  const cwd = path.dirname(runnerPath);
  // -u / PYTHONUNBUFFERED: force unbuffered stdout/stderr so output streams immediately
  const child = spawn(pythonExe, ["-u", runnerPath, "--shell-id", shellId, "--server", serverUrl], {
    cwd,
    env: { ...process.env, PYTHONIOENCODING: "utf-8", PYTHONUNBUFFERED: "1" },
    detached: false,
  });

  if (!child.pid) {
    return { ok: false, error: "Failed to spawn process (no PID assigned)" };
  }

  registry.set(shellId, child);

  // Write stdout/stderr to a file so logs survive Next.js HMR reloads
  child.stdout?.on("data", (chunk: Buffer) => appendLog(shellId, chunk));
  child.stderr?.on("data", (chunk: Buffer) => appendLog(shellId, chunk));

  await pool.query(
    `INSERT INTO resource_processes (shell_id, pid, started_at)
     VALUES ($1, $2, NOW())
     ON CONFLICT (shell_id) DO UPDATE SET pid = EXCLUDED.pid, started_at = EXCLUDED.started_at`,
    [shellId, child.pid]
  );

  child.on("exit", (code, signal) => {
    appendLog(shellId, `\n[process exited — code=${code ?? "null"} signal=${signal ?? "null"}]`);
    registry.delete(shellId);
    pool.query("DELETE FROM resource_processes WHERE shell_id = $1", [shellId]).catch(() => {});
  });

  return { ok: true, pid: child.pid };
}

export const LINE_CONTROLLER_ID = "line-controller";

export async function startLineController(): Promise<StartResult> {
  await ensureTable();

  const existing = registry.get(LINE_CONTROLLER_ID);
  if (existing && existing.exitCode === null && existing.signalCode === null) {
    return { ok: false, error: "Already running" };
  }
  if (existing) registry.delete(LINE_CONTROLLER_ID);

  const { scriptPath, pythonExe } = getLineControllerConfig();
  if (!scriptPath) {
    return { ok: false, error: "Line Controller path not configured. Set it in the Line Controller settings." };
  }

  clearProcessLogs(LINE_CONTROLLER_ID);

  const cwd = path.dirname(scriptPath);
  const child = spawn(pythonExe, ["-u", scriptPath], {
    cwd,
    env: { ...process.env, PYTHONIOENCODING: "utf-8", PYTHONUNBUFFERED: "1" },
    detached: false,
  });

  if (!child.pid) {
    return { ok: false, error: "Failed to spawn process (no PID assigned)" };
  }

  registry.set(LINE_CONTROLLER_ID, child);

  child.stdout?.on("data", (chunk: Buffer) => appendLog(LINE_CONTROLLER_ID, chunk));
  child.stderr?.on("data", (chunk: Buffer) => appendLog(LINE_CONTROLLER_ID, chunk));

  await pool.query(
    `INSERT INTO resource_processes (shell_id, pid, started_at)
     VALUES ($1, $2, NOW())
     ON CONFLICT (shell_id) DO UPDATE SET pid = EXCLUDED.pid, started_at = EXCLUDED.started_at`,
    [LINE_CONTROLLER_ID, child.pid]
  );

  child.on("exit", (code, signal) => {
    appendLog(LINE_CONTROLLER_ID, `\n[process exited — code=${code ?? "null"} signal=${signal ?? "null"}]`);
    registry.delete(LINE_CONTROLLER_ID);
    pool.query("DELETE FROM resource_processes WHERE shell_id = $1", [LINE_CONTROLLER_ID]).catch(() => {});
  });

  return { ok: true, pid: child.pid };
}

export const MES_API_ID = "mes-api";

export async function startMesApi(): Promise<StartResult> {
  await ensureTable();

  const existing = registry.get(MES_API_ID);
  if (existing && existing.exitCode === null && existing.signalCode === null) {
    return { ok: false, error: "Already running" };
  }
  if (existing) registry.delete(MES_API_ID);

  const { scriptPath, pythonExe, port } = getMesApiConfig();
  if (!scriptPath) {
    return { ok: false, error: "MES API path not configured. Set it in the MES API settings." };
  }

  clearProcessLogs(MES_API_ID);

  const cwd = path.dirname(scriptPath);
  const moduleName = path.basename(scriptPath, ".py");
  const child = spawn(
    pythonExe,
    ["-u", "-m", "uvicorn", `${moduleName}:app`, "--host", "0.0.0.0", "--port", String(port)],
    {
      cwd,
      env: { ...process.env, PYTHONIOENCODING: "utf-8", PYTHONUNBUFFERED: "1" },
      detached: false,
    }
  );

  if (!child.pid) {
    return { ok: false, error: "Failed to spawn process (no PID assigned)" };
  }

  registry.set(MES_API_ID, child);

  child.stdout?.on("data", (chunk: Buffer) => appendLog(MES_API_ID, chunk));
  child.stderr?.on("data", (chunk: Buffer) => appendLog(MES_API_ID, chunk));

  await pool.query(
    `INSERT INTO resource_processes (shell_id, pid, started_at)
     VALUES ($1, $2, NOW())
     ON CONFLICT (shell_id) DO UPDATE SET pid = EXCLUDED.pid, started_at = EXCLUDED.started_at`,
    [MES_API_ID, child.pid]
  );

  child.on("exit", (code, signal) => {
    appendLog(MES_API_ID, `\n[process exited — code=${code ?? "null"} signal=${signal ?? "null"}]`);
    registry.delete(MES_API_ID);
    pool.query("DELETE FROM resource_processes WHERE shell_id = $1", [MES_API_ID]).catch(() => {});
  });

  return { ok: true, pid: child.pid };
}

export async function stopRunner(shellId: string): Promise<{ ok: boolean; error?: string }> {
  await ensureTable();

  const child = registry.get(shellId);
  if (child && child.exitCode === null && child.signalCode === null) {
    child.kill("SIGTERM");
    registry.delete(shellId);
    await pool.query("DELETE FROM resource_processes WHERE shell_id = $1", [shellId]);
    return { ok: true };
  }

  // Fallback: orphaned PID from DB (post-restart scenario)
  const result = await pool.query("SELECT pid FROM resource_processes WHERE shell_id = $1", [shellId]);
  if (result.rows.length > 0) {
    const pid = (result.rows[0] as { pid: number }).pid;
    try { process.kill(pid, "SIGTERM"); } catch { /* already gone */ }
    await pool.query("DELETE FROM resource_processes WHERE shell_id = $1", [shellId]);
    return { ok: true };
  }

  return { ok: false, error: "No running process found for this shell" };
}
