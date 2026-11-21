/** A MITRE tag as returned by the API (core.mitre.mitre_for_rules). */
export interface MitreTag {
  id: string;
  label: string;
  name: string;
  tactic: string;
  url: string;
}

export function mitreTagFrom(value: string | MitreTag): MitreTag {
  if (typeof value === "string") {
    return {
      id: value,
      label: value,
      name: "",
      tactic: "",
      url: `https://attack.mitre.org/techniques/${encodeURIComponent(value.replaceAll(".", "/"))}/`,
    };
  }
  return value;
}

export function mitreKey(value: string | MitreTag): string {
  return typeof value === "string" ? value : value.id;
}
