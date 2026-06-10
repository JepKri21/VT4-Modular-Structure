import { NextResponse } from "next/server";
import { getLiveShellIds, MES_API_ID } from "@/lib/process-registry";
import { getMesApiConfig } from "@/lib/aas-config";
import { pool } from "@/lib/db";

export interface MesApiStatus {
  running: boolean;
  pid?: number;
  port: number;
  configOk: boolean;
}

export async function GET(): Promise<NextResponse<MesApiStatus>> {
  const { scriptPath, port } = getMesApiConfig();
  const liveIds = await getLiveShellIds();
  const running = liveIds.has(MES_API_ID);

  let pid: number | undefined;
  if (running) {
    const rows = await pool.query("SELECT pid FROM resource_processes WHERE shell_id = $1", [MES_API_ID]);
    pid = (rows.rows[0] as { pid?: number } | undefined)?.pid;
  }

  return NextResponse.json({ running, pid, port, configOk: scriptPath !== "" });
}
