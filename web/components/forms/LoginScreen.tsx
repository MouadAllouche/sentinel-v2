"use client";

import { useState } from "react";

import { ApiError } from "@/lib/api/client";
import { useLogin } from "@/lib/api/hooks";
import { validateNextPath } from "@/lib/auth";

import { LoginForm, type LoginValues } from "./LoginForm";
import { useTheme } from "@/components/layout/ThemeProvider";

export function LoginScreen() {
  const login = useLogin();
  const { theme, toggle } = useTheme();
  const [next] = useState(() => {
    if (typeof window === "undefined") return "/";
    return validateNextPath(new URLSearchParams(window.location.search).get("next"));
  });
  const [error, setError] = useState<string | null>(null);

  const onSubmit = async (values: LoginValues) => {
    setError(null);
    try {
      await login.mutateAsync(values);
      window.location.assign(next);
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 429) {
        setError("Too many attempts. Please try again later.");
      } else {
        setError("Invalid credentials");
      }
    }
  };

  return (
    <main className="mx-auto flex min-h-screen max-w-sm flex-col justify-center gap-6 p-4">
      <div className="flex justify-end">
        <button
          type="button"
          aria-label="Theme"
          aria-pressed={theme === "dark"}
          onClick={toggle}
          className="rounded border border-slate-300 px-2 py-1 text-sm dark:border-slate-600"
        >
          {theme === "dark" ? "Light" : "Dark"}
        </button>
      </div>
      <div>
        <h1 className="text-2xl font-semibold">Sign in to Sentinel</h1>
        <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
          Read-only monitoring. Your session is managed by the server.
        </p>
      </div>
      <LoginForm onSubmit={onSubmit} error={error} />
    </main>
  );
}
