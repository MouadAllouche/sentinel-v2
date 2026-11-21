import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, openSync, closeSync, readFileSync } from "node:fs";
import path from "node:path";

/** Generate the e2e demo DB synchronously, before Playwright starts webServers. */
export function ensureDemo(): { username: string; viewer: string; password: string } {
  const projectRoot = path.resolve(__dirname, "..", "..");
  const workdir = path.join(projectRoot, ".demo-e2e");
  const credentialsPath = path.join(workdir, "credentials.json");
  const lockPath = path.join(workdir, ".seed.lock");

  if (!existsSync(credentialsPath)) {
    mkdirSync(workdir, { recursive: true });
    let lock: number | undefined;
    try {
      // Only one config loader seeds on a fresh checkout; the others wait for
      // the credentials file that the winner writes.
      lock = openSync(lockPath, "wx");
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
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "EEXIST") throw error;
      // Another loader is seeding; wait until its credentials file appears.
      const deadline = Date.now() + 120_000;
      while (!existsSync(credentialsPath) && Date.now() < deadline) {
        const shared = new Int32Array(new SharedArrayBuffer(4));
        Atomics.wait(shared, 0, 0, 250);
      }
      if (!existsSync(credentialsPath)) throw new Error("timed out waiting for demo seed");
    } finally {
      if (lock !== undefined) {
        closeSync(lock);
        try {
          require("node:fs").unlinkSync(lockPath);
        } catch {
          // best effort
        }
      }
    }
  }

  return JSON.parse(readFileSync(credentialsPath, "utf-8")) as {
    username: string;
    viewer: string;
    password: string;
  };
}
