"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button, Input, Label } from "@/components/ui/primitives";

const schema = z.object({
  username: z.string().min(1, "Username is required"),
  password: z.string().min(1, "Password is required"),
});

export type LoginValues = z.infer<typeof schema>;

export function LoginForm({
  onSubmit,
  error,
}: {
  onSubmit: (values: LoginValues) => void | Promise<void>;
  error: string | null;
}) {
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginValues>({ resolver: zodResolver(schema), defaultValues: { username: "", password: "" } });

  return (
    <form
      noValidate
      method="post"
      action="/login"
      className="space-y-4"
      onSubmit={handleSubmit(async (values) => {
        await onSubmit(values);
      })}
    >
      <div>
        <Label htmlFor="username">Username</Label>
        <Input
          id="username"
          autoComplete="username"
          aria-invalid={Boolean(errors.username)}
          aria-describedby={errors.username ? "username-error" : undefined}
          {...register("username")}
        />
        {errors.username ? (
          <p id="username-error" role="alert" className="mt-1 text-sm text-red-700 dark:text-red-300">
            {errors.username.message}
          </p>
        ) : null}
      </div>
      <div>
        <Label htmlFor="password">Password</Label>
        <Input
          id="password"
          type="password"
          autoComplete="current-password"
          aria-invalid={Boolean(errors.password)}
          aria-describedby={errors.password ? "password-error" : undefined}
          {...register("password")}
        />
        {errors.password ? (
          <p id="password-error" role="alert" className="mt-1 text-sm text-red-700 dark:text-red-300">
            {errors.password.message}
          </p>
        ) : null}
      </div>
      {error ? (
        <p role="alert" aria-live="polite" className="rounded border border-red-300 bg-red-50 p-2 text-sm text-red-900 dark:border-red-700 dark:bg-red-950 dark:text-red-100">
          {error}
        </p>
      ) : null}
      <Button type="submit" disabled={isSubmitting} className="w-full">
        Sign in
      </Button>
    </form>
  );
}
