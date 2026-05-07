import { useEffect } from "react";

import { api } from "../api/client";

export function useProjectStream(projectId: number | null, onEvent: () => void): void {
  useEffect(() => {
    if (!projectId) {
      return;
    }
    const source = new EventSource(`${api.apiBaseUrl}/api/projects/${projectId}/stream`);
    source.onmessage = () => {
      onEvent();
    };
    source.onerror = () => {
      source.close();
    };
    return () => source.close();
  }, [projectId, onEvent]);
}

