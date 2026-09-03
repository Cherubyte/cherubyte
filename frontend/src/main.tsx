import React from "react";
import ReactDOM from "react-dom/client";
import { App } from "./App";
import { registerServiceWorker } from "./lib/push";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);

// Register the push service worker after first paint so a delivered alert can
// wake it even when the panel tab is closed. No-op where the APIs are missing.
registerServiceWorker();
