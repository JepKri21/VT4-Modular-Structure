import { NextResponse } from "next/server";
import { getLiveShellIds, LINE_CONTROLLER_ID } from "@/lib/process-registry";
import { getLineControllerConfig } from "@/lib/aas-config";
import { pool } from "@/lib/db";

export interface LineControllerStatus {
  running: boolean;
  pid?: number;
  configOk: boolean;
}

export async function GET(): Promise<NextResponse<LineControllerStatus>> {
  const { scriptPath } = getLineControllerConfig();
  const liveIds = await getLiveShellIds();
  const running = liveIds.has(LINE_CONTROLLER_ID);

  let pid: number | undefined;
  if (running) {
    const rows = await pool.query("SELECT pid FROM resource_processes WHERE shell_id = $1", [LINE_CONTROLLER_ID]);
    pid = (rows.rows[0] as { pid?: number } | undefined)?.pid;
  }

  return NextResponse.json({ running, pid, configOk: scriptPath !== "" });
}
