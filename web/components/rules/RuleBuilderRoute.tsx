"use client";

import { useParams } from "next/navigation";

import { RuleBuilder } from "./RuleBuilder";
import { ErrorState } from "@/components/ui/primitives";

export function RuleBuilderRoute() {
  const params = useParams<{ id: string }>();
  return params.id ? <RuleBuilder id={params.id} /> : <ErrorState message="Invalid rule id." />;
}
