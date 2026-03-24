import { useState, useEffect, useCallback } from "react";
import type { AppConfig } from "../types/config";
import { defaultAppConfig } from "../config/gauges";

const CONFIG_API = import.meta.env.VITE_GOPRO_API_URL ?? "http://localhost:3001";

export function useConfig() {
  const [config, setConfig] = useState<AppConfig>(defaultAppConfig);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`${CONFIG_API}/api/config`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data: AppConfig = await res.json();
        if (!cancelled) {
          setConfig(data);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(String(err));
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const saveConfig = useCallback(async (newConfig: AppConfig) => {
    try {
      const res = await fetch(`${CONFIG_API}/api/config`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(newConfig),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail ?? `HTTP ${res.status}`);
      }
      const saved: AppConfig = await res.json();
      setConfig(saved);
      setError(null);
      return { ok: true as const };
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(msg);
      return { ok: false as const, error: msg };
    }
  }, []);

  const resetToDefaults = useCallback(async () => {
    try {
      const res = await fetch(`${CONFIG_API}/api/config/defaults`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const defaults: AppConfig = await res.json();
      const result = await saveConfig(defaults);
      if (result.ok) {
        return { ok: true as const, config: defaults };
      }
      return result;
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(msg);
      return { ok: false as const, error: msg };
    }
  }, [saveConfig]);

  return { config, loading, error, saveConfig, resetToDefaults };
}
