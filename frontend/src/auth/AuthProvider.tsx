import { useQuery } from "@tanstack/react-query";
import { createContext, useContext, type ReactNode } from "react";
import { api } from "../api/client";
import type { Account, AccountRole } from "../api/types";

type AuthValue = {
  account: Account | null;
  setupRequired: boolean;
  isLoading: boolean;
};

const AuthContext = createContext<AuthValue | null>(null);

/** Query key other code can invalidate to force a re-check (e.g. after a 401). */
export const AUTH_KEY = ["auth", "status"] as const;

export function AuthProvider({ children }: { children: ReactNode }) {
  const q = useQuery({
    queryKey: AUTH_KEY,
    queryFn: api.authStatus,
    retry: false,
    staleTime: 30_000,
  });

  const value: AuthValue = {
    account: q.data?.account ?? null,
    setupRequired: q.data?.setup_required ?? false,
    isLoading: q.isLoading,
  };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const v = useContext(AuthContext);
  if (!v) throw new Error("useAuth outside AuthProvider");
  return v;
}

export function useAccount(): Account | null {
  return useAuth().account;
}

const RANK: Record<AccountRole, number> = { viewer: 0, editor: 1, admin: 2 };

export function useCanWrite(): boolean {
  const a = useAccount();
  return !!a && RANK[a.role] >= RANK.editor;
}

export function useIsAdmin(): boolean {
  return useAccount()?.role === "admin";
}
