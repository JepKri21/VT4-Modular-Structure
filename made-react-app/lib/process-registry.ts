import { ChildProcess, spawn } from "child_process";
import path from "path";
import { pool } from "@/lib/db";
import { CREATE_RESOURCE_PROCESSES_TABLE_SQL } from "@/lib/inventory";
import { getResourceRunnerConfig } from "@/lib/aas-config";

// Module-level singleton — one instance per Next.js server process
const registry = new Map<string, ChildProcess>();

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

  const cwd = path.dirname(runnerPath);
  const child = spawn(pythonExe, [runnerPath, "--shell-id", shellId, "--server", serverUrl], {
    cwd,
    env: { ...process.env, PYTHONIOENCODING: "utf-8" },
    detached: false,
  });

  if (!child.pid) {
    return { ok: false, error: "Failed to spawn process (no PID assigned)" };
  }

  registry.set(shellId, child);

  await pool.query(
    `INSERT INTO resource_processes (shell_id, pid, started_at)
     VALUES ($1, $2, NOW())
     ON CONFLICT (shell_id) DO UPDATE SET pid = EXCLUDED.pid, started_at = EXCLUDED.started_at`,
    [shellId, child.pid]
  );

  child.on("exit", () => {
    registry.delete(shellId);
    pool.query("DELETE FROM resource_processes WHERE shell_id = $1", [shellId]).catch(() => {});
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
