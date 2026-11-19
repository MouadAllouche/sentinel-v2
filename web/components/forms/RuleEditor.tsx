"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button, Input, Label } from "@/components/ui/primitives";
import { useToast } from "@/components/ui/Toaster";
import { ApiError, client } from "@/lib/api/client";
import { useRule } from "@/lib/api/hooks";
import { RequireRole } from "@/lib/auth";

const schema = z.object({
  name: z.string().min(1, "Name is required"),
  definition: z
    .string()
    .min(1, "Definition is required")
    .refine((value) => {
      try {
        JSON.parse(value);
        return true;
      } catch {
        return false;
      }
    }, "Definition must be valid JSON"),
});

type Values = z.infer<typeof schema>;

export function RuleEditor() {
  const params = useParams<{ id?: string }>();
  const id = params?.id;
  const router = useRouter();
  const rule = useRule(id);
  const [serverError, setServerError] = useState<string | null>(null);
  const { show } = useToast();
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting, isDirty },
  } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { name: "", definition: "{}" },
    values: rule.data
      ? {
          name: String(rule.data.name ?? ""),
          definition: JSON.stringify(rule.data, null, 2),
        }
      : undefined,
  });

  useEffect(() => {
    if (!isDirty) return;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [isDirty]);

  const onSubmit = handleSubmit(async (values) => {
    setServerError(null);
    try {
      const definition = JSON.parse(values.definition) as Record<string, unknown>;
      if (id) {
        await client.PUT("/api/rules/{identifier}", {
          params: { path: { identifier: id } },
          body: { definition },
        });
      } else {
        await client.POST("/api/rules", { body: { definition } });
      }
      router.push("/rules");
    } catch (cause) {
      const message =
        cause instanceof ApiError
          ? cause.details?.map((detail) => `${detail.path}: ${detail.message}`).join("; ") ||
            cause.message
          : "Could not save the rule";
      setServerError(message);
      show(message);
      if (cause instanceof ApiError) {
        for (const detail of cause.details ?? []) {
          const field = detail.path.includes("name") ? "name" : "definition";
          setError(field, { type: "server", message: detail.message });
        }
      }
    }
  });

  return (
    <RequireRole requiredRole="admin">
      <div className="max-w-3xl space-y-4">
        <h1 className="text-xl font-semibold">{id ? "Edit rule" : "New rule"}</h1>
        <form className="space-y-3" noValidate onSubmit={onSubmit}>
          <div>
            <Label htmlFor="rule-name">Name</Label>
            <Input
              id="rule-name"
              {...register("name")}
              aria-invalid={Boolean(errors.name)}
              aria-describedby={errors.name ? "rule-name-error" : undefined}
            />
            {errors.name ? (
              <p id="rule-name-error" role="alert" className="text-sm text-red-700">
                {errors.name.message}
              </p>
            ) : null}
          </div>
          <div>
            <Label htmlFor="rule-definition">Definition (JSON)</Label>
            <textarea
              id="rule-definition"
              rows={16}
              className="w-full rounded border border-slate-300 bg-white p-2 font-mono text-sm dark:border-slate-600 dark:bg-slate-800"
              {...register("definition")}
              aria-invalid={Boolean(errors.definition)}
              aria-describedby={errors.definition ? "rule-definition-error" : undefined}
            />
            {errors.definition ? (
              <p id="rule-definition-error" role="alert" className="text-sm text-red-700">
                {errors.definition.message}
              </p>
            ) : null}
          </div>
          {serverError ? (
            <p role="alert" className="rounded border border-red-300 bg-red-50 p-2 text-sm text-red-900">
              {serverError}
            </p>
          ) : null}
          <Button type="submit" disabled={isSubmitting}>Save rule</Button>
        </form>
      </div>
    </RequireRole>
  );
}
