import { NextRequest, NextResponse } from "next/server";
import { spawn } from "child_process";
import { getGeneratorPath } from "@/lib/aas-config";

export async function POST(req: NextRequest) {
  const { serverUrl, dryRun } = await req.json() as { serverUrl: string; dryRun?: boolean };

  if (!serverUrl?.trim()) {
    return NextResponse.json({ error: "serverUrl is required" }, { status: 400 });
  }

  const generatorPath = getGeneratorPath();
  const args = ["upload_templates.py", "--url", serverUrl.trim()];
  if (dryRun) args.push("--dry-run");

  return new Promise<NextResponse>((resolve) => {
    const child = spawn("python", args, {
      cwd: generatorPath,
      env: { ...process.env, PYTHONIOENCODING: "utf-8" },
    });

    let output = "";
    child.stdout.on("data", (chunk: Buffer) => { output += chunk.toString(); });
    child.stderr.on("data", (chunk: Buffer) => { output += chunk.toString(); });

    child.on("close", (exitCode) => {
      resolve(NextResponse.json({ output, exitCode: exitCode ?? 1 }));
    });

    child.on("error", (err) => {
      resolve(NextResponse.json({ output: `Failed to spawn Python: ${err.message}`, exitCode: 1 }));
    });
  });
}
