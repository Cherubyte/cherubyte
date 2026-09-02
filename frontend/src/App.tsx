import {
  MutationCache,
  QueryCache,
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query";
import { createBrowserRouter, RouterProvider } from "react-router-dom";
import { ApiError } from "./api/client";
import { AUTH_KEY, AuthProvider, useAuth } from "./auth/AuthProvider";
import { I18nProvider } from "./i18n";
import { Shell } from "./components/Shell";
import { ToasterProvider } from "./components/Toaster";
import { Approvals } from "./pages/Approvals";
import { Dashboard } from "./pages/Dashboard";
import { DeviceDetail } from "./pages/DeviceDetail";
import { Distribution } from "./pages/Distribution";
import { DistributionDetail } from "./pages/DistributionDetail";
import { Events } from "./pages/Events";
import { Login } from "./pages/Login";
import { Settings } from "./pages/Settings";
import { Topology } from "./pages/Topology";
import { UserDetail } from "./pages/UserDetail";
import { Users } from "./pages/Users";

/** When any request comes back 401 the session is gone — re-check auth so the
 * app falls back to the login screen instead of showing broken pages. */
function onError(err: unknown) {
  if (err instanceof ApiError && err.status === 401) {
    qc.invalidateQueries({ queryKey: AUTH_KEY });
  }
}

const qc = new QueryClient({
  defaultOptions: { queries: { staleTime: 5000, retry: 1, refetchOnWindowFocus: false } },
  queryCache: new QueryCache({ onError }),
  mutationCache: new MutationCache({ onError }),
});

const router = createBrowserRouter([
  {
    path: "/",
    element: <RequireAuth />,
    children: [
      { index: true, element: <Dashboard /> },
      { path: "devices/:id", element: <DeviceDetail /> },
      { path: "approvals", element: <Approvals /> },
      { path: "distribution", element: <Distribution /> },
      { path: "distribution/:kind/:name", element: <DistributionDetail /> },
      { path: "users", element: <Users /> },
      { path: "users/:id", element: <UserDetail /> },
      { path: "events", element: <Events /> },
      { path: "topology", element: <Topology /> },
      { path: "settings", element: <Settings /> },
    ],
  },
]);

function RequireAuth() {
  const { account, setupRequired, isLoading } = useAuth();
  if (isLoading) return <div className="min-h-screen bg-bg" />;
  if (!account) return <Login setupRequired={setupRequired} />;
  return <Shell />;
}

export function App() {
  return (
    <QueryClientProvider client={qc}>
      <I18nProvider>
        <ToasterProvider>
          <AuthProvider>
            <RouterProvider router={router} />
          </AuthProvider>
        </ToasterProvider>
      </I18nProvider>
    </QueryClientProvider>
  );
}
