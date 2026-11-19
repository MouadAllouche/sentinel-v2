"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button, Input, Label } from "@/components/ui/primitives";
import { useToast } from "@/components/ui/Toaster";
import { ApiError, client } from "@/lib/api/client";

const schema = z
  .object({
    old_password: z.string().min(1, "Current password is required"),
    new_password: z.string().min(12, "New password must be at least 12 characters"),
  })
  .refine((values) => values.old_password !== values.new_password, {
    path: ["new_password"],
    message: "Choose a different password",
  });

type Values = z.infer<typeof schema>;

export function ChangePasswordDialog({ onClose }: { onClose: () => void }) {
  const { show } = useToast();
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<Values>({ resolver: zodResolver(schema) });

  const onSubmit = handleSubmit(async (values) => {
    try {
      await client.POST("/api/auth/password", { body: values });
      show("Password changed", "success");
      onClose();
    } catch (cause) {
      show(cause instanceof ApiError ? cause.message : "Could not change the password");
    }
  });

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Change password"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
    >
      <form
        noValidate
        onSubmit={onSubmit}
        className="w-full max-w-sm space-y-3 rounded-lg bg-white p-5 shadow-xl dark:bg-slate-900"
      >
        <h2 className="text-lg font-semibold">Change password</h2>
        <div>
          <Label htmlFor="old-password">Current password</Label>
          <Input id="old-password" type="password" autoComplete="current-password" {...register("old_password")} />
          {errors.old_password ? (
            <p role="alert" className="text-sm text-red-700">{errors.old_password.message}</p>
          ) : null}
        </div>
        <div>
          <Label htmlFor="new-password">New password</Label>
          <Input id="new-password" type="password" autoComplete="new-password" {...register("new_password")} />
          {errors.new_password ? (
            <p role="alert" className="text-sm text-red-700">{errors.new_password.message}</p>
          ) : null}
        </div>
        <div className="flex justify-end gap-2">
          <Button onClick={onClose}>Cancel</Button>
          <Button type="submit" disabled={isSubmitting}>Change password</Button>
        </div>
      </form>
    </div>
  );
}
