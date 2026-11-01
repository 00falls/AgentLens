import { useState, type ReactNode } from "react";

let apiKey = "";
export function authFetch(path: RequestInfo | URL, options: RequestInit = {}) {
  const headers = new Headers(options.headers);
  headers.set("Authorization", `Bearer ${apiKey}`);
  return globalThis.fetch(path, { ...options, headers });
}

export function AuthGate({ children }: { children: (project: string, logout: () => void) => ReactNode }) {
  const [key, setKey] = useState("");
  const [project, setProject] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  function logout() { apiKey = ""; setKey(""); setProject(""); }
  if (project) return children(project, logout);
  return <main className="login"><form className="panel" onSubmit={async e => {
    e.preventDefault(); setBusy(true); setError("");
    try {
      const r = await globalThis.fetch("/identity", { headers: { Authorization: `Bearer ${key}` } });
      if (!r.ok) throw new Error(`身份验证失败 (${r.status})`);
      const data = await r.json(); apiKey = key; setKey(""); setProject(data.project);
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }}><p className="eyebrow">AGENTLENS · 工作空间</p><h1>连接项目</h1>
    <p className="muted">使用绑定项目的演示 API Key。凭证仅保留在当前页面内存。</p>
    <label>API Key<input type="password" autoComplete="off" value={key} onChange={e => setKey(e.target.value)} required /></label>
    {error && <p role="alert" className="error">{error}</p>}
    <button disabled={busy}>{busy ? "验证中…" : "进入工作台"}</button>
  </form></main>;
}
