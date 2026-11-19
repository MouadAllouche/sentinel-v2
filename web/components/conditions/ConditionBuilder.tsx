"use client";

import { Button } from "@/components/ui/primitives";
import { describeCondition, validateRegex } from "@/lib/rules/helpers";

const OPS = ["eq", "ne", "in", "not_in", "contains", "regex", "gte", "lte", "exists", "cidr_in"];
const FIELDS = ["event_type", "source", "username", "source_ip", "process_name", "details.*", "enrichment.*"];

export function ConditionBuilder({
  value,
  onChange,
  depth = 0,
  maxDepth = 4,
  disabled = false,
}: {
  value: unknown;
  onChange: (value: unknown) => void;
  depth?: number;
  maxDepth?: number;
  disabled?: boolean;
}) {
  const node = value && typeof value === "object" ? (value as Record<string, unknown>) : { all: [] };
  const children = Array.isArray(node.all) ? node.all : [];
  const regexCondition = children.find((child) => {
    const item = child as Record<string, unknown>;
    return item.op === "regex";
  }) as Record<string, unknown> | undefined;
  const regexSource = String(regexCondition?.regex ?? regexCondition?.value ?? "");
  const regexError = regexSource ? validateRegex(regexSource) : null;

  return (
    <section aria-label="Condition builder" className="space-y-2 rounded border border-slate-200 p-3 dark:border-slate-700">
      <div className="flex flex-wrap items-center gap-2">
        <label className="text-sm">
          Match
          <select
            aria-label="Condition group"
            className="ml-2 rounded border border-slate-300 px-2 py-1 dark:border-slate-600 dark:bg-slate-800"
            value={node.all ? "all" : node.any ? "any" : "not"}
            onChange={(event) => {
              const key = event.target.value;
              onChange({ [key]: children });
            }}
          >
            <option value="all">ALL</option>
            <option value="any">ANY</option>
            <option value="not">NOT</option>
          </select>
        </label>
        <Button
          aria-label="Add condition"
          disabled={disabled || depth >= maxDepth}
          onClick={() =>
            onChange({ ...node, all: [...children, { field: "event_type", op: "eq", value: "" }] })
          }
        >
          Add condition
        </Button>
        {depth >= maxDepth ? <p className="text-xs text-amber-800">Maximum nesting depth reached.</p> : null}
      </div>
      <ul className="space-y-2">
        {children.map((child, index) => {
          const condition = child as Record<string, unknown>;
          return (
            <li key={index} className="flex flex-wrap items-center gap-2">
              <select
                aria-label={`Condition ${index + 1} field`}
                disabled={disabled}
                className="rounded border border-slate-300 px-2 py-1 dark:border-slate-600 dark:bg-slate-800"
                value={String(condition.field ?? "")}
                onChange={(event) =>
                  onChange({ ...node, all: children.map((item, position) => position === index ? { ...condition, field: event.target.value } : item) })
                }
              >
                {FIELDS.map((field) => <option key={field} value={field}>{field}</option>)}
              </select>
              <select
                aria-label={`Condition ${index + 1} operator`}
                disabled={disabled}
                className="rounded border border-slate-300 px-2 py-1 dark:border-slate-600 dark:bg-slate-800"
                value={String(condition.op ?? "eq")}
                onChange={(event) =>
                  onChange({ ...node, all: children.map((item, position) => position === index ? { ...condition, op: event.target.value } : item) })
                }
              >
                {OPS.map((op) => <option key={op} value={op}>{op}</option>)}
              </select>
              <input
                aria-label={`Condition ${index + 1} value`}
                disabled={disabled}
                className="rounded border border-slate-300 px-2 py-1 dark:border-slate-600 dark:bg-slate-800"
                value={String(condition.value ?? "")}
                onChange={(event) => {
                  const next = children.map((item, position) =>
                    position === index
                      ? { ...condition, value: event.target.value, regex: condition.op === "regex" ? event.target.value : undefined }
                      : item,
                  );
                  onChange({ ...node, all: next });
                }}
              />
              {condition.op === "regex" ? (
                <p role="status" className="w-full text-xs">
                  {regexError ?? "Regex length ≤ 200 characters; nested quantifiers are rejected; input limited to 500 characters."}
                </p>
              ) : null}
              {depth + 1 < maxDepth ? (
                <ConditionBuilder
                  value={condition.all ?? condition.any ?? { all: [] }}
                  depth={depth + 1}
                  maxDepth={maxDepth}
                  onChange={(nested) =>
                    onChange({ ...node, all: children.map((item, position) => position === index ? { ...condition, all: nested } : item) })
                  }
                />
              ) : null}
            </li>
          );
        })}
      </ul>
      <p data-testid="condition-describe" className="text-sm text-slate-600 dark:text-slate-300">
        describe: {describeCondition(value) || "no conditions"}
      </p>
    </section>
  );
}
