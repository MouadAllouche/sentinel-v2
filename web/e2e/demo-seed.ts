import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync } from "node:fs";
import path from "node:path";

/** Generate the e2e demo DB synchronously, before Playwright starts webServers. */
export function ensureDemo(): { username: string; viewer: string; password: string } {
  const projectRoot = path.resolve(__dirname, "..", "..");
  const workdir = path.join(projectRoot, ".demo-e2e");
  const credentialsPath = path.join(workdir, "credentials.json");
  if (!existsSync(credentialsPath)) {
    mkdirSync(workdir, { recursive: true });
    const python = path.join(projectRoot, "venv", "bin", "python");
    const result = spawnSync(
      python,
      [
        path.join(projectRoot, "cli.py"),
        "demo",
        "--reset",
        "--no-print-password",
        "--workdir",
        workdir,
      ],
      { cwd: projectRoot, encoding: "utf-8", timeout: 120_000 },
    );
    if (result.status !== 0) {
      throw new Error(`demo generation failed: ${result.stderr || result.stdout}`);
    }
  }
  return JSON.parse(readFileSync(credentialsPath, "utf-8")) as {
    username: string;
    viewer: string;
    password: string;
  };
}
