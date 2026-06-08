"use client";

import { useState, useEffect, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Power,
  Play,
  Square,
  RefreshCw,
  Settings,
  AlertTriangle,
  Loader2,
  ChevronDown,
  ChevronUp,
  Terminal,
} from "lucide-react";
import type { ResourceControlEntry, ResourceControlResponse } from "@/app/api/resource-control/route";

type ResourceState = ResourceControlEntry & { toggling: boolean };

export default function ResourceControlPage() {
  const [serverUrl, setServerUrl] = useState("http://localhost:8081");
  const [resources, setResources] = useState<ResourceState[]>([]);
  const [configOk, setConfigOk] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [runnerPath, setRunnerPath] = useState("");
  const [pythonExe, setPythonExe] = useState("python");
  const [configSaving, setConfigSaving] = useState(false);
  const [configSaved, setConfigSaved] = useState(false);
  const [expandedLogs, setExpandedLogs] = useState<Set<string>>(new Set());
  const [logLines, setLogLines] = useState<Record<string, string[]>>({});

  const fetchLogs = useCallback(async (shellId: string) => {
    try {
      const res = await fetch(`/api/resource-control/logs?shellId=${encodeURIComponent(shellId)}`);
      const data = await res.json() as { lines: string[] };
      setLogLines((prev) => ({ ...prev, [shellId]: data.lines }));
    } catch { /* ignore */ }
  }, []);

  const toggleLogs = useCallback((shellId: string) => {
    setExpandedLogs((prev) => {
      const next = new Set(prev);
      if (next.has(shellId)) { next.delete(shellId); } else { next.add(shellId); void fetchLogs(shellId); }
      return next;
    });
  }, [fetchLogs]);

  // Poll logs for all expanded panels every 2 seconds
  useEffect(() => {
    if (expandedLogs.size === 0) return;
    const id = setInterval(() => {
      for (const shellId of expandedLogs) void fetchLogs(shellId);
    }, 2000);
    return () => clearInterval(id);
  }, [expandedLogs, fetchLogs]);

  const fetchResources = useCallback(async (url = serverUrl) => {
    try {
      const res = await fetch(`/api/resource-control?serverUrl=${encodeURIComponent(url)}`);
      const data: ResourceControlResponse = await res.json();
      setConfigOk(data.configOk);
      setError(data.error ?? null);
      setResources((prev) => {
        const toggling = new Set(prev.filter((r) => r.toggling).map((r) => r.shellId));
        return data.resources.map((r) => ({
          ...r,
          toggling: toggling.has(r.shellId),
        }));
      });
    } catch (err) {
      setError(`Failed to fetch resources: ${String(err)}`);
    }
  }, [serverUrl]);

  // Initial load + load runner config
  useEffect(() => {
    setLoading(true);
    fetchResources().finally(() => setLoading(false));
    fetch("/api/resource-control/config")
      .then((r) => r.json())
      .then((cfg: { runnerPath: string; pythonExe: string }) => {
        setRunnerPath(cfg.runnerPath ?? "");
        setPythonExe(cfg.pythonExe ?? "python");
      })
      .catch(() => {});
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Auto-refresh every 5 seconds
  useEffect(() => {
    const id = setInterval(() => fetchResources(), 5000);
    return () => clearInterval(id);
  }, [fetchResources]);

  const handleToggle = async (shellId: string, currentlyRunning: boolean) => {
    // Optimistic update
    setResources((prev) =>
      prev.map((r) =>
        r.shellId === shellId ? { ...r, running: !currentlyRunning, toggling: true } : r
      )
    );

    try {
      if (currentlyRunning) {
        await fetch("/api/resource-control/stop", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ shellId }),
        });
      } else {
        await fetch("/api/resource-control/start", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ shellId, serverUrl }),
        });
      }
    } catch {
      // Reconcile on next poll
    } finally {
      setResources((prev) =>
        prev.map((r) => (r.shellId === shellId ? { ...r, toggling: false } : r))
      );
      // Immediate reconcile
      await fetchResources();
    }
  };

  const handleSaveConfig = async () => {
    setConfigSaving(true);
    try {
      await fetch("/api/resource-control/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ runnerPath, pythonExe }),
      });
      setConfigSaved(true);
      setTimeout(() => setConfigSaved(false), 2000);
      await fetchResources();
    } finally {
      setConfigSaving(false);
    }
  };

  const runningCount = resources.filter((r) => r.running).length;

  return (
    <div className="p-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <Power className="w-6 h-6 text-primary" />
          <h1 className="text-2xl font-bold">Resource Control</h1>
          <span className="text-sm text-muted-foreground bg-muted px-2 py-0.5 rounded-full">
            {runningCount} / {resources.length} running
          </span>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => fetchResources()}
            disabled={loading}
          >
            <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setSettingsOpen((v) => !v)}
          >
            <Settings className="w-4 h-4 mr-1" />
            Settings
            {settingsOpen ? <ChevronUp className="w-3 h-3 ml-1" /> : <ChevronDown className="w-3 h-3 ml-1" />}
          </Button>
        </div>
      </div>

      {/* Settings panel */}
      {settingsOpen && (
        <Card className="mb-6">
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Runner Configuration</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-end gap-3">
              <div className="flex-1">
                <label htmlFor="serverUrl" className="text-sm font-medium mb-1 block">AAS Server URL</label>
                <Input
                  id="serverUrl"
                  value={serverUrl}
                  onChange={(e) => setServerUrl(e.target.value)}
                  placeholder="http://localhost:8081"
                />
              </div>
              <Button variant="secondary" onClick={() => fetchResources()}>
                Connect
              </Button>
            </div>
            <div>
              <label htmlFor="runnerPath" className="text-sm font-medium mb-1 block">Generic Resource Runner path</label>
              <Input
                id="runnerPath"
                value={runnerPath}
                onChange={(e) => setRunnerPath(e.target.value)}
                placeholder="C:\...\Generic_Resource_Runner\Generic_Resource_Runner.py"
                className="font-mono text-sm"
              />
            </div>
            <div className="flex items-end gap-3">
              <div className="w-48">
                <label htmlFor="pythonExe" className="text-sm font-medium mb-1 block">Python executable</label>
                <Input
                  id="pythonExe"
                  value={pythonExe}
                  onChange={(e) => setPythonExe(e.target.value)}
                  placeholder="python"
                  className="font-mono text-sm"
                />
              </div>
              <Button onClick={handleSaveConfig} disabled={configSaving}>
                {configSaving ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : null}
                {configSaved ? "Saved!" : "Save"}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Config warning */}
      {!configOk && (
        <div className="flex items-center gap-2 mb-4 p-3 rounded-lg bg-yellow-500/10 border border-yellow-500/30 text-yellow-600 dark:text-yellow-400">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          <span className="text-sm">
            Runner not configured — open Settings and set the path to{" "}
            <code className="text-xs font-mono">Generic_Resource_Runner.py</code>.
          </span>
        </div>
      )}

      {/* AAS error */}
      {error && (
        <div className="flex items-center gap-2 mb-4 p-3 rounded-lg bg-destructive/10 border border-destructive/30 text-destructive">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          <span className="text-sm">{error}</span>
        </div>
      )}

      {/* Resource grid */}
      {resources.length === 0 && !loading && !error && (
        <p className="text-muted-foreground text-sm text-center py-12">
          No resource instances found on the AAS server.
        </p>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {resources.map((resource) => (
          <Card key={resource.shellId} className="relative">
            <CardContent className="p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-start gap-3 min-w-0">
                  {/* Status dot */}
                  <span
                    className={`mt-1 shrink-0 w-2.5 h-2.5 rounded-full ${
                      resource.running ? "bg-green-500" : "bg-muted-foreground/30"
                    }`}
                  />
                  <div className="min-w-0">
                    <p className="font-semibold text-sm leading-tight truncate">
                      {resource.displayName}
                    </p>
                    <p className="text-xs text-muted-foreground font-mono truncate mt-0.5">
                      {resource.shellId.length > 60
                        ? `…${resource.shellId.slice(-55)}`
                        : resource.shellId}
                    </p>
                    {resource.running && resource.pid && (
                      <span className="mt-1 inline-block text-xs bg-green-500/10 text-green-600 dark:text-green-400 px-1.5 py-0.5 rounded font-mono">
                        PID: {resource.pid}
                      </span>
                    )}
                    {resource.running && !resource.pid && (
                      <span className="mt-1 inline-block text-xs bg-green-500/10 text-green-600 dark:text-green-400 px-1.5 py-0.5 rounded">
                        running
                      </span>
                    )}
                  </div>
                </div>

                <div className="flex items-center gap-1 shrink-0">
                  {/* Logs toggle */}
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => toggleLogs(resource.shellId)}
                    title="Toggle logs"
                  >
                    <Terminal className="w-3.5 h-3.5" />
                  </Button>

                  {/* Start/Stop button */}
                  <Button
                    size="sm"
                    variant={resource.running ? "destructive" : "default"}
                    disabled={resource.toggling || (!configOk && !resource.running)}
                    onClick={() => handleToggle(resource.shellId, resource.running)}
                  >
                    {resource.toggling ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : resource.running ? (
                      <>
                        <Square className="w-3.5 h-3.5 mr-1" />
                        Stop
                      </>
                    ) : (
                      <>
                        <Play className="w-3.5 h-3.5 mr-1" />
                        Start
                      </>
                    )}
                  </Button>
                </div>
              </div>

              {/* Log panel */}
              {expandedLogs.has(resource.shellId) && (
                <div className="mt-3 rounded-md bg-black/80 border border-border overflow-hidden">
                  <div className="px-2 py-1 text-xs text-muted-foreground border-b border-border flex items-center gap-1">
                    <Terminal className="w-3 h-3" />
                    stdout / stderr
                  </div>
                  <pre className="p-2 text-xs font-mono text-green-400 overflow-auto max-h-48 whitespace-pre-wrap break-all">
                    {(logLines[resource.shellId] ?? []).length === 0
                      ? <span className="text-muted-foreground italic">No output yet…</span>
                      : (logLines[resource.shellId] ?? []).join("\n")}
                  </pre>
                </div>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
