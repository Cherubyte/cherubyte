import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";

/**
 * Subscribes to the backend SSE feed and invalidates queries as things change,
 * so the UI stays live without polling hard.
 */
export function useStream() {
  const qc = useQueryClient();

  useEffect(() => {
    const es = new EventSource("/api/stream");

    const refetchAll = () => {
      qc.invalidateQueries({ queryKey: ["devices"] });
      qc.invalidateQueries({ queryKey: ["stats"] });
      qc.invalidateQueries({ queryKey: ["events"] });
      qc.invalidateQueries({ queryKey: ["users"] });
    };

    for (const evt of [
      "scan_complete",
      "device_new",
      "device_online",
      "device_offline",
      "scan_error",
      "scan_empty",
    ]) {
      es.addEventListener(evt, refetchAll);
    }

    es.onerror = () => {
      /* EventSource auto-reconnects */
    };

    return () => es.close();
  }, [qc]);
}
