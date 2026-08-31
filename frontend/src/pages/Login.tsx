import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api/client";
import { AUTH_KEY } from "../auth/AuthProvider";
import { Button, Field } from "../components/ui";
import { AppMark } from "../components/Glyph";
import { useT } from "../i18n";

export function Login({ setupRequired }: { setupRequired: boolean }) {
  const qc = useQueryClient();
  const t = useT();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");

  const submit = useMutation({
    mutationFn: () =>
      setupRequired
        ? api.setup(username.trim(), password)
        : api.login(username.trim(), password),
    onSuccess: () => qc.invalidateQueries({ queryKey: AUTH_KEY }),
  });

  const mismatch = setupRequired && confirm.length > 0 && confirm !== password;
  const canSubmit =
    username.trim().length >= 2 &&
    password.length >= (setupRequired ? 8 : 1) &&
    !mismatch;

  return (
    <div className="flex min-h-screen items-center justify-center bg-bg px-4">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex items-center gap-2.5">
          <AppMark size={24} className="text-fg" />
          <span className="font-display text-[17px] text-fg">NetScan</span>
        </div>
        <div className="panel p-7">
          <h1 className="font-display mb-1 text-[22px] text-fg">
            {t(setupRequired ? "auth.setup.title" : "auth.login.title")}
          </h1>
          <p className="mb-5 text-[12.5px] text-fg-3">
            {t(setupRequired ? "auth.setup.sub" : "auth.login.sub")}
          </p>
          <form
            className="space-y-3.5"
            onSubmit={(e) => {
              e.preventDefault();
              if (canSubmit) submit.mutate();
            }}
          >
            <Field label={t("auth.field.username")}>
              <input
                className="input"
                autoFocus
                autoComplete="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
              />
            </Field>
            <Field label={t("auth.field.password")}>
              <input
                className="input"
                type="password"
                autoComplete={setupRequired ? "new-password" : "current-password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </Field>
            {setupRequired && (
              <Field
                label={t("auth.field.confirm")}
                error={mismatch ? t("auth.field.mismatch") : undefined}
              >
                <input
                  className="input"
                  type="password"
                  autoComplete="new-password"
                  value={confirm}
                  onChange={(e) => setConfirm(e.target.value)}
                />
              </Field>
            )}
            {submit.isError && (
              <p className="text-[12px] text-alert">
                {t(setupRequired ? "auth.setup.failed" : "auth.login.failed")}
              </p>
            )}
            <Button
              type="submit"
              variant="primary"
              className="w-full"
              loading={submit.isPending}
              disabled={!canSubmit}
            >
              {t(setupRequired ? "auth.setup.submit" : "auth.login.submit")}
            </Button>
          </form>
        </div>
      </div>
    </div>
  );
}
