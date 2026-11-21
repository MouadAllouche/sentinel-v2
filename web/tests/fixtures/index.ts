/** Load the API-generated fixtures committed under web/tests/fixtures. */
export function fixture<T = Record<string, unknown>>(name: string): T {
  const json = require(`./${name}.json`) as T;
  return json;
}

export interface MitreTag {
  id: string;
  label: string;
  name: string;
  tactic: string;
  url: string;
}
