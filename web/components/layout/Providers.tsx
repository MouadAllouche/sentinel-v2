"use client";

import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

import { client } from "@/lib/api/client";
import { AuthContext, type Me } from "@/lib/auth";
import { queryKeys } from "@/lib/query-keys";
import { ToastProvider } from "@/components/ui/Toaster";

import { ThemeProvider } from "./ThemeProvider";

const anonymous: Me = { username: "", role: "viewer" };

function AuthProvider({ children }: { children: ReactNode }) {
  const query = useQuery({
    queryKey: queryKeys.me,
    queryFn: async (): Promise<Me> => {
      const { data } = await client.GET("/api/auth/me");
      return (data as Me | undefined) ?? anonymous;
    },
    retry: false,
    staleTime: 5 * 60 * 1000,
  });

  return <AuthContext.Provider value={query.data ?? anonymous}>{children}</AuthContext.Provider>;
}

export function Providers({ children }: { children: ReactNode }) {
  const [queryClient] = useState(
    () => new QueryClient({ defaultOptions: { queries: { staleTime: 15_000, retry: 1 } } }),
  );

  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <ToastProvider>
          <AuthProvider>{children}</AuthProvider>
        </ToastProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
}
