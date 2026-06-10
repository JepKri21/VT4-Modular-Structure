"use client";

import { useState, useEffect, useCallback, useRef } from "react";
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
  X,
  Network,
} from "lucide-react";
import type { ResourceControlEntry, ResourceControlResponse } from "@/app/api/resource-control/route";
import type { LineControllerStatus } from "@/app/api/line-controller/route";
import type { MesApiStatus } from "@/app/api/mes-controller/route";

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

  // Line Controller state
  const [lcStatus, setLcStatus] = useState<LineControllerStatus>({ running: false, configOk: false });
  const [lcToggling, setLcToggling] = useState(false);
  const [lcLogsOpen, setLcLogsOpen] = useState(false);
  const [lcLogLines, setLcLogLines] = useState<string[]>([]);
  const [lcScriptPath, setLcScriptPath] = useState("");
  const [lcPythonExe, setLcPythonExe] = useState("python");
  const [lcConfigSaving, setLcConfigSaving] = useState(false);
  const [lcConfigSaved, setLcConfigSaved] = useState(false);
  const [lcSettingsOpen, setLcSettingsOpen] = useState(false);
  const logEndRef = useRef<HTMLDivElement>(null);

  // MES API state
  const [mesStatus, setMesStatus] = useState<MesApiStatus>({ running: false, configOk: false, port: 8000 });
  const [mesToggling, setMesToggling] = useState(false);
  const [mesLogsOpen, setMesLogsOpen] = useState(false);
  const [mesLogLines, setMesLogLines] = useState<string[]>([]);
  const [mesScriptPath, setMesScriptPath] = useState("");
  const [mesPythonExe, setMesPythonExe] = useState("python");
  const [mesPort, setMesPort] = useState(8000);
  const [mesConfigSaving, setMesConfigSaving] = useState(false);
  const [mesConfigSaved, setMesConfigSaved] = useState(false);
  const [mesSettingsOpen, setMesSettingsOpen] = useState(false);
  const mesLogEndRef = useRef<HTMLDivElement>(null);

  const fetchLcStatus = useCallback(async () => {
    try {
      const res = await fetch("/api/line-controller");
      const data = await res.json() as LineControllerStatus;
      setLcStatus(data);
    } catch { /* ignore */ }
  }, []);

  const fetchLcLogs = useCallback(async () => {
    try {
      const res = await fetch("/api/line-controller/logs");
      const data = await res.json() as { lines: string[] };
      setLcLogLines(data.lines);
    } catch { /* ignore */ }
  }, []);

  const fetchMesStatus = useCallback(async () => {
    try {
      const res = await fetch("/api/mes-controller");
      const data = await res.json() as MesApiStatus;
      setMesStatus(data);
    } catch { /* ignore */ }
  }, []);

  const fetchMesLogs = useCallback(async () => {
    try {
      const res = await fetch("/api/mes-controller/logs");
      const data = await res.json() as { lines: string[] };
      setMesLogLines(data.lines);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    if (mesLogsOpen) mesLogEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [mesLogLines, mesLogsOpen]);

  useEffect(() => {
    if (!mesLogsOpen) return;
    void fetchMesLogs();
    const id = setInterval(() => void fetchMesLogs(), 1500);
    return () => clearInterval(id);
  }, [mesLogsOpen, fetchMesLogs]);

  useEffect(() => {
    void fetchMesStatus();
    const id = setInterval(() => void fetchMesStatus(), 5000);
    return () => clearInterval(id);
  }, [fetchMesStatus]);

  useEffect(() => {
    fetch("/api/mes-controller/config")
      .then((r) => r.json())
      .then((cfg: { scriptPath: string; pythonExe: string; port: number }) => {
        setMesScriptPath(cfg.scriptPath ?? "");
        setMesPythonExe(cfg.pythonExe ?? "python");
        setMesPort(cfg.port ?? 8000);
      })
      .catch(() => {});
  }, []);

  const handleMesToggle = async () => {
    setMesToggling(true);
    try {
      if (mesStatus.running) {
        await fetch("/api/mes-controller/stop", { method: "POST" });
      } else {
        await fetch("/api/mes-controller/start", { method: "POST" });
      }
    } finally {
      setMesToggling(false);
      await fetchMesStatus();
    }
  };

  const handleMesSaveConfig = async () => {
    setMesConfigSaving(true);
    try {
      await fetch("/api/mes-controller/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scriptPath: mesScriptPath, pythonExe: mesPythonExe, port: mesPort }),
      });
      setMesConfigSaved(true);
      setTimeout(() => setMesConfigSaved(false), 2000);
      await fetchMesStatus();
    } finally {
      setMesConfigSaving(false);
    }
  };

  // Auto-scroll logs to bottom
  useEffect(() => {
    if (lcLogsOpen) logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [lcLogLines, lcLogsOpen]);

  // Poll LC logs when modal is open
  useEffect(() => {
    if (!lcLogsOpen) return;
    void fetchLcLogs();
    const id = setInterval(() => void fetchLcLogs(), 1500);
    return () => clearInterval(id);
  }, [lcLogsOpen, fetchLcLogs]);

  // Poll LC status every 5s
  useEffect(() => {
    void fetchLcStatus();
    const id = setInterval(() => void fetchLcStatus(), 5000);
    return () => clearInterval(id);
  }, [fetchLcStatus]);

  // Load LC config on mount
  useEffect(() => {
    fetch("/api/line-controller/config")
      .then((r) => r.json())
      .then((cfg: { scriptPath: string; pythonExe: string }) => {
        setLcScriptPath(cfg.scriptPath ?? "");
        setLcPythonExe(cfg.pythonExe ?? "python");
      })
      .catch(() => {});
  }, []);

  const handleLcToggle = async () => {
    setLcToggling(true);
    try {
      if (lcStatus.running) {
        await fetch("/api/line-controller/stop", { method: "POST" });
      } else {
        await fetch("/api/line-controller/start", { method: "POST" });
      }
    } finally {
      setLcToggling(false);
      await fetchLcStatus();
    }
  };

  const handleLcSaveConfig = async () => {
    setLcConfigSaving(true);
    try {
      await fetch("/api/line-controller/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scriptPath: lcScriptPath, pythonExe: lcPythonExe }),
      });
      setLcConfigSaved(true);
      setTimeout(() => setLcConfigSaved(false), 2000);
      await fetchLcStatus();
    } finally {
      setLcConfigSaving(false);
    }
  };

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

      {/* Section: Resources */}
      <div className="flex items-center gap-3 mb-3">
        <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider">Resources</h2>
        <div className="flex-1 h-px bg-border" />
      </div>

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

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 mb-8">
        {resources.map((resource) => (
          <Card key={resource.shellId} className={`relative border-2 ${resource.running ? "border-green-500/40" : "border-border"}`}>
            <CardContent className="p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-start gap-3 min-w-0">
                  <span
                    className={`mt-1 shrink-0 w-2.5 h-2.5 rounded-full ${
                      resource.running ? "bg-green-500 shadow-[0_0_6px_2px_rgba(34,197,94,0.5)]" : "bg-muted-foreground/30"
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
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => toggleLogs(resource.shellId)}
                    title="Toggle logs"
                  >
                    <Terminal className="w-3.5 h-3.5" />
                  </Button>

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

      {/* Section: System Services */}
      <div className="flex items-center gap-3 mb-3">
        <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider">System Services</h2>
        <div className="flex-1 h-px bg-border" />
      </div>

      {/* Line Controller card */}
      <Card className={`mb-4 border-2 ${lcStatus.running ? "border-green-500/40" : "border-border"}`}>
        <CardContent className="p-4">
          <div className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-3 min-w-0">
              <span
                className={`shrink-0 w-3 h-3 rounded-full ${
                  lcStatus.running ? "bg-green-500 shadow-[0_0_6px_2px_rgba(34,197,94,0.5)]" : "bg-muted-foreground/30"
                }`}
              />
              <Network className="w-5 h-5 text-primary shrink-0" />
              <div className="min-w-0">
                <p className="font-semibold text-sm">Line Controller</p>
                <p className="text-xs text-muted-foreground">
                  {lcStatus.running
                    ? `Running${lcStatus.pid ? ` · PID ${lcStatus.pid}` : ""}`
                    : "Stopped"}
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2 shrink-0">
              <Button
                size="sm"
                variant="ghost"
                onClick={() => { setLcLogsOpen(true); void fetchLcLogs(); }}
                title="Open command output"
              >
                <Terminal className="w-3.5 h-3.5 mr-1" />
                Output
              </Button>

              <Button
                size="sm"
                variant="ghost"
                onClick={() => setLcSettingsOpen((v) => !v)}
                title="Configure Line Controller path"
              >
                <Settings className="w-3.5 h-3.5" />
              </Button>

              <Button
                size="sm"
                variant={lcStatus.running ? "destructive" : "default"}
                disabled={lcToggling || (!lcStatus.configOk && !lcStatus.running)}
                onClick={handleLcToggle}
              >
                {lcToggling ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : lcStatus.running ? (
                  <><Square className="w-3.5 h-3.5 mr-1" />Stop</>
                ) : (
                  <><Play className="w-3.5 h-3.5 mr-1" />Start</>
                )}
              </Button>
            </div>
          </div>

          {/* Inline config for Line Controller */}
          {lcSettingsOpen && (
            <div className="mt-4 pt-4 border-t border-border space-y-3">
              <div>
                <label className="text-xs font-medium mb-1 block text-muted-foreground">Path to main.py</label>
                <Input
                  value={lcScriptPath}
                  onChange={(e) => setLcScriptPath(e.target.value)}
                  placeholder="C:\...\Line_Controller\main.py"
                  className="font-mono text-xs"
                />
              </div>
              <div className="flex items-end gap-3">
                <div className="w-40">
                  <label className="text-xs font-medium mb-1 block text-muted-foreground">Python executable</label>
                  <Input
                    value={lcPythonExe}
                    onChange={(e) => setLcPythonExe(e.target.value)}
                    placeholder="python"
                    className="font-mono text-xs"
                  />
                </div>
                <Button size="sm" onClick={handleLcSaveConfig} disabled={lcConfigSaving}>
                  {lcConfigSaving ? <Loader2 className="w-3.5 h-3.5 animate-spin mr-1" /> : null}
                  {lcConfigSaved ? "Saved!" : "Save"}
                </Button>
              </div>
            </div>
          )}

          {!lcStatus.configOk && (
            <div className="mt-3 flex items-center gap-2 text-xs text-yellow-600 dark:text-yellow-400">
              <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
              Path not configured — click <Settings className="w-3 h-3 inline mx-0.5" /> and set the path to <code className="font-mono">main.py</code>.
            </div>
          )}
        </CardContent>
      </Card>

      {/* MES API card */}
      <Card className={`mb-6 border-2 ${mesStatus.running ? "border-green-500/40" : "border-border"}`}>
        <CardContent className="p-4">
          <div className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-3 min-w-0">
              <span
                className={`shrink-0 w-3 h-3 rounded-full ${
                  mesStatus.running ? "bg-green-500 shadow-[0_0_6px_2px_rgba(34,197,94,0.5)]" : "bg-muted-foreground/30"
                }`}
              />
              <Power className="w-5 h-5 text-primary shrink-0" />
              <div className="min-w-0">
                <p className="font-semibold text-sm">MES API</p>
                <p className="text-xs text-muted-foreground">
                  {mesStatus.running
                    ? `Running on :${mesStatus.port}${mesStatus.pid ? ` · PID ${mesStatus.pid}` : ""}`
                    : `Stopped · port ${mesStatus.port}`}
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2 shrink-0">
              <Button
                size="sm"
                variant="ghost"
                onClick={() => { setMesLogsOpen(true); void fetchMesLogs(); }}
                title="Open command output"
              >
                <Terminal className="w-3.5 h-3.5 mr-1" />
                Output
              </Button>

              <Button
                size="sm"
                variant="ghost"
                onClick={() => setMesSettingsOpen((v) => !v)}
                title="Configure MES API path"
              >
                <Settings className="w-3.5 h-3.5" />
              </Button>

              <Button
                size="sm"
                variant={mesStatus.running ? "destructive" : "default"}
                disabled={mesToggling || (!mesStatus.configOk && !mesStatus.running)}
                onClick={handleMesToggle}
              >
                {mesToggling ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : mesStatus.running ? (
                  <><Square className="w-3.5 h-3.5 mr-1" />Stop</>
                ) : (
                  <><Play className="w-3.5 h-3.5 mr-1" />Start</>
                )}
              </Button>
            </div>
          </div>

          {mesSettingsOpen && (
            <div className="mt-4 pt-4 border-t border-border space-y-3">
              <div>
                <label className="text-xs font-medium mb-1 block text-muted-foreground">Path to mes_api.py</label>
                <Input
                  value={mesScriptPath}
                  onChange={(e) => setMesScriptPath(e.target.value)}
                  placeholder="C:\...\MES\mes_api.py"
                  className="font-mono text-xs"
                />
              </div>
              <div className="flex items-end gap-3">
                <div className="w-40">
                  <label className="text-xs font-medium mb-1 block text-muted-foreground">Python executable</label>
                  <Input
                    value={mesPythonExe}
                    onChange={(e) => setMesPythonExe(e.target.value)}
                    placeholder="python"
                    className="font-mono text-xs"
                  />
                </div>
                <div className="w-28">
                  <label className="text-xs font-medium mb-1 block text-muted-foreground">Port</label>
                  <Input
                    type="number"
                    value={mesPort}
                    onChange={(e) => setMesPort(Number(e.target.value))}
                    placeholder="8000"
                    className="font-mono text-xs"
                  />
                </div>
                <Button size="sm" onClick={handleMesSaveConfig} disabled={mesConfigSaving}>
                  {mesConfigSaving ? <Loader2 className="w-3.5 h-3.5 animate-spin mr-1" /> : null}
                  {mesConfigSaved ? "Saved!" : "Save"}
                </Button>
              </div>
            </div>
          )}

          {!mesStatus.configOk && (
            <div className="mt-3 flex items-center gap-2 text-xs text-yellow-600 dark:text-yellow-400">
              <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
              Path not configured — click <Settings className="w-3 h-3 inline mx-0.5" /> and set the path to <code className="font-mono">mes_api.py</code>.
            </div>
          )}
        </CardContent>
      </Card>

      {/* MES API log modal */}
      {mesLogsOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
          onClick={(e) => { if (e.target === e.currentTarget) setMesLogsOpen(false); }}
        >
          <div className="relative w-full max-w-3xl mx-4 rounded-xl border border-border bg-background shadow-2xl flex flex-col"
               style={{ maxHeight: "80vh" }}>
            <div className="flex items-center justify-between px-4 py-3 border-b border-border shrink-0">
              <div className="flex items-center gap-2">
                <Terminal className="w-4 h-4 text-primary" />
                <span className="font-semibold text-sm">MES API — Output</span>
                <span className={`w-2 h-2 rounded-full ${mesStatus.running ? "bg-green-500" : "bg-muted-foreground/30"}`} />
                <span className="text-xs text-muted-foreground">
                  {mesStatus.running ? `running :${mesStatus.port}` : "stopped"}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <Button size="sm" variant="ghost" onClick={() => void fetchMesLogs()} title="Refresh">
                  <RefreshCw className="w-3.5 h-3.5" />
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setMesLogsOpen(false)}>
                  <X className="w-4 h-4" />
                </Button>
              </div>
            </div>
            <div className="overflow-auto flex-1 bg-black/90 rounded-b-xl p-3">
              <pre className="text-xs font-mono text-green-400 whitespace-pre-wrap break-all leading-relaxed">
                {mesLogLines.length === 0
                  ? <span className="text-muted-foreground italic">No output yet…</span>
                  : mesLogLines.join("\n")}
              </pre>
              <div ref={mesLogEndRef} />
            </div>
            <div className="px-4 py-2 border-t border-border shrink-0 flex items-center justify-between">
              <span className="text-xs text-muted-foreground">{mesLogLines.length} lines · auto-refreshes every 1.5 s</span>
              <Button
                size="sm"
                variant={mesStatus.running ? "destructive" : "default"}
                disabled={mesToggling || (!mesStatus.configOk && !mesStatus.running)}
                onClick={handleMesToggle}
              >
                {mesToggling ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin mr-1" />
                ) : mesStatus.running ? (
                  <><Square className="w-3 h-3 mr-1" />Stop</>
                ) : (
                  <><Play className="w-3 h-3 mr-1" />Start</>
                )}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Line Controller log modal */}
      {lcLogsOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
          onClick={(e) => { if (e.target === e.currentTarget) setLcLogsOpen(false); }}
        >
          <div className="relative w-full max-w-3xl mx-4 rounded-xl border border-border bg-background shadow-2xl flex flex-col"
               style={{ maxHeight: "80vh" }}>
            {/* Modal header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-border shrink-0">
              <div className="flex items-center gap-2">
                <Terminal className="w-4 h-4 text-primary" />
                <span className="font-semibold text-sm">Line Controller — Output</span>
                <span
                  className={`w-2 h-2 rounded-full ${lcStatus.running ? "bg-green-500" : "bg-muted-foreground/30"}`}
                />
                <span className="text-xs text-muted-foreground">
                  {lcStatus.running ? "running" : "stopped"}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => void fetchLcLogs()}
                  title="Refresh"
                >
                  <RefreshCw className="w-3.5 h-3.5" />
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setLcLogsOpen(false)}>
                  <X className="w-4 h-4" />
                </Button>
              </div>
            </div>

            {/* Log output */}
            <div className="overflow-auto flex-1 bg-black/90 rounded-b-xl p-3">
              <pre className="text-xs font-mono text-green-400 whitespace-pre-wrap break-all leading-relaxed">
                {lcLogLines.length === 0
                  ? <span className="text-muted-foreground italic">No output yet…</span>
                  : lcLogLines.join("\n")}
              </pre>
              <div ref={logEndRef} />
            </div>

            {/* Modal footer */}
            <div className="px-4 py-2 border-t border-border shrink-0 flex items-center justify-between">
              <span className="text-xs text-muted-foreground">{lcLogLines.length} lines · auto-refreshes every 1.5 s</span>
              <Button
                size="sm"
                variant={lcStatus.running ? "destructive" : "default"}
                disabled={lcToggling || (!lcStatus.configOk && !lcStatus.running)}
                onClick={handleLcToggle}
              >
                {lcToggling ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin mr-1" />
                ) : lcStatus.running ? (
                  <><Square className="w-3 h-3 mr-1" />Stop</>
                ) : (
                  <><Play className="w-3 h-3 mr-1" />Start</>
                )}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
