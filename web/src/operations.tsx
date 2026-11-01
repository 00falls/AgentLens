import { useEffect, useState } from "react";
import { authFetch } from "./auth";

type Summary = { runs: number; tool_errors: number; input_tokens: number; output_tokens: number;
  billing: { currency: string; total: string | null; known_subtotal: string; unknown_calls: number } };
type Event = { id: string; timestamp: string; actor: string; action: string; resource: string;
  run_id: string | null; decision: string; result: string };
export function Operations({ project, onRun }: { project: string; onRun: (id: string) => void }) {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [events, setEvents] = useState<Event[]>([]);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    Promise.all(["/operations", "/audit-events"].map(async path => {
      const r = await authFetch(path, { headers: { "X-AgentLens-Project": project }, signal: controller.signal });
      if (!r.ok) throw new Error(`读取失败 (${r.status})`);
      return r.json();
    })).then(([s, a]) => { setSummary(s); setEvents(a.events); setError(""); })
      .catch(e => { if (e.name !== "AbortError") setError(e.message); });
    return () => controller.abort();
  }, [project, refresh]);
  return <section className="panel operations"><div className="section-heading"><div>
    <p className="eyebrow">OPERATIONS</p><h2>用量与审计</h2></div><button onClick={() => setRefresh(x => x + 1)}>刷新</button></div>
    <p className="muted">费用按模型步骤累计。历史调用缺少完整计价依据时，总额显示未知；不重复累计 Span。</p>
    {error && <p role="alert">{error}</p>}
    {summary && <div className="execution-modes">
      <article><h3>运行 / 工具错误</h3><strong>{summary.runs} / {summary.tool_errors}</strong></article>
      <article><h3>输入 / 输出 Token</h3><strong>{summary.input_tokens} / {summary.output_tokens}</strong></article>
      <article><h3>费用（USD）</h3><strong>{summary.billing.total ?? "未知"}</strong>
        <p>已知部分 ${summary.billing.known_subtotal}；{summary.billing.unknown_calls} 次调用未完整计价</p></article>
    </div>}
    <h3>最近授权与执行事件</h3><div className="table-scroll"><table><thead><tr>
      <th>时间 / 执行者</th><th>动作 / 资源</th><th>决定 / 结果</th><th>运行</th>
    </tr></thead><tbody>{events.map(e => <tr key={e.id}>
      <td>{new Date(e.timestamp).toLocaleString("zh-CN")}<br/>{e.actor}</td>
      <td>{e.action}<br/><span className="muted">{e.resource}</span></td>
      <td>{e.decision} / {e.result}</td><td>{e.run_id ? <button className="run-link" onClick={() => onRun(e.run_id!)}>{e.run_id}</button> : "—"}</td>
    </tr>)}</tbody></table></div>
  </section>;
}
