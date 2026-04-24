import { NextRequest, NextResponse } from "next/server";
import { spawn } from "child_process";
import path from "path";
import { getGeneratorPath } from "@/lib/aas-config";

function runPython(payload: unknown): Promise<Record<string, unknown>> {
  const generatorPath = getGeneratorPath();
  const scriptPath = path.join(generatorPath, "form_to_aas.py");
  return new Promise((resolve, reject) => {
    const child = spawn("python", [scriptPath], { cwd: generatorPath });

    let stdout = "";
    let stderr = "";

    child.stdout.on("data", (chunk: Buffer) => { stdout += chunk.toString(); });
    child.stderr.on("data", (chunk: Buffer) => { stderr += chunk.toString(); });

    child.on("close", (code) => {
      if (code !== 0) {
        reject(new Error(stderr || `Python exited with code ${code}`));
        return;
      }
      try {
        resolve(JSON.parse(stdout));
      } catch {
        reject(new Error(`Failed to parse Python output: ${stdout.slice(0, 200)}`));
      }
    });

    child.on("error", (err) => {
      reject(new Error(`Failed to spawn Python: ${err.message}`));
    });

    child.stdin.write(JSON.stringify(payload));
    child.stdin.end();
  });
}

export async function POST(req: NextRequest) {
  const payload = await req.json();

  try {
    const env = await runPython(payload);
    return NextResponse.json(env);
  } catch (err) {
    return NextResponse.json(
      { error: String(err) },
      { status: 500 }
    );
  }
}
