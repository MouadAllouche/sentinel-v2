import { Button } from "@/components/ui/primitives";

export function VersionHistory({
  versions,
  onRestore,
}: {
  versions: Array<{ version: number; created_at: string; actor?: string }>;
  onRestore: (version: number) => void;
}) {
  return (
    <section aria-label="Version history">
      <h2 className="mb-2 font-semibold">Version history</h2>
      <ul className="space-y-2 text-sm">
        {versions.length === 0 ? <li className="text-slate-500">No versions yet.</li> : null}
        {versions.map((version) => (
          <li key={version.version} className="flex items-center gap-2 rounded border border-slate-200 p-2 dark:border-slate-700">
            <span>Version {version.version} · {version.created_at}</span>
            <Button onClick={() => onRestore(version.version)} aria-label={`Restore version ${version.version}`}>
              Restore version {version.version}
            </Button>
          </li>
        ))}
      </ul>
    </section>
  );
}
