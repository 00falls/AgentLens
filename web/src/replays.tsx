import { useEffect, useState } from "react";

type Recording = {
  recording_id: string;
  source_run_id: string;
  sha256: string;
  tool_calls: number;
};
type Scenario = {
  scenario_id: string;
  source_run_id: string | null;
  sha256: string;
  case_id: string;
};
type Run = {
  run_id: string;
  input: string;
  status: string;
  execution_mode: string;
  source_run_id: string | null;
};
type Fact = {
  code: string;
  observed?: unknown;
  expected?: unknown;
  location?: { run_id: string; step_sequence?: number; field: string };
  locations?: { run_id: string; step_sequence?: number; field: string }[];
};
type Difference = {
  baseline_run_id: string;
  candidate_run_id: string;
  candidate_mode: string;
  tool_calls: {
    baseline: unknown[];
    candidate: unknown[];
    baseline_counts: Record<string, number>;
    candidate_counts: Record<string, number>;
  };
  citations: { added: string[]; removed: string[] };
  answers: { baseline: unknown; candidate: unknown };
  usage: { delta: Record<string, number> };
  duration_ms: { delta: number | null };
  facts: { baseline: Fact[]; candidate: Fact[] };
  evaluation: {
    baseline: { passed: boolean };
    candidate: { passed: boolean };
  } | null;
};
const modes: Record<string, string> = {
  live: "现场执行",
  recorded_replay: "录制重跑",
  frozen_scenario: "冻结场景评测",
};

export function Replays({
  project,
  onRun,
}: {
  project: string;
  onRun: (id: string, sequence?: number) => void;
}) {
  const [recordings, setRecordings] = useState<Recording[]>([]);
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [runs, setRuns] = useState<Run[]>([]);
  const [source, setSource] = useState("");
  const [recording, setRecording] = useState("");
  const [scenario, setScenario] = useState("");
  const [candidate, setCandidate] = useState("");
  const [model, setModel] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [comparison, setComparison] = useState<Difference | null>(null);
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setComparison(null);
    setError("");
    async function load() {
      const headers = { "X-AgentLens-Project": project };
      const results = await Promise.all(
        ["/recordings", "/scenarios", "/runs?limit=100"].map(async (path) => {
          const r = await fetch(path, { headers, signal: controller.signal });
          if (!r.ok) throw new Error(`读取失败 (${r.status})`);
          return r.json();
        }),
      );
      setRecordings(results[0].recordings);
      setScenarios(results[1].scenarios);
      setRuns(results[2].runs);
      setRecording(
        (previous) => previous || results[0].recordings[0]?.recording_id || "",
      );
      setScenario(
        (previous) => previous || results[1].scenarios[0]?.scenario_id || "",
      );
      setSource(
        (previous) =>
          previous ||
          results[0].recordings[0]?.source_run_id ||
          results[2].runs[0]?.run_id ||
          "",
      );
      setCandidate(
        (previous) =>
          previous ||
          results[2].runs.find((r: Run) => r.execution_mode !== "live")
            ?.run_id ||
          "",
      );
    }
    load().catch((e) => {
      if (e.name !== "AbortError") setError(e.message);
    });
    return () => controller.abort();
  }, [project, refresh]);
  useEffect(() => {
    setComparison(null);
    setError("");
    if (!source || !candidate) return;
    const controller = new AbortController();
    const params = new URLSearchParams({ baseline: source, candidate });
    fetch(`/run-comparison?${params}`, {
      headers: { "X-AgentLens-Project": project },
      signal: controller.signal,
    })
      .then(async (r) => {
        if (!r.ok)
          throw new Error(`差异查询失败 (${r.status})：${await r.text()}`);
        return r.json();
      })
      .then(setComparison)
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => controller.abort();
  }, [source, candidate, project, refresh]);
  async function act(path: string, body: unknown) {
    setBusy(true);
    setError("");
    try {
      const r = await fetch(path, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-AgentLens-Project": project,
        },
        body: JSON.stringify(body),
      });
      const value = await r.json();
      if (!r.ok && !(r.status === 409 && value.status === "replay_mismatch"))
        throw new Error(JSON.stringify(value));
      if (value.run_id) setCandidate(value.run_id);
      if (value.recording_id) {
        setRecording(value.recording_id);
        setSource(value.source_run_id);
      }
      if (value.scenario_id) {
        setScenario(value.scenario_id);
        if (value.source_run_id) setSource(value.source_run_id);
      }
      setRefresh((n) => n + 1);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">CONTROLLED RERUN</p>
          <h1>
            改变决策，保留证据边界<span>。</span>
          </h1>
          <p className="subtitle">
            历史查看不调用模型。录制重跑与冻结场景评测会调用模型，结果可能变化。
          </p>
        </div>
      </div>
      <section className="panel evaluation-panel">
        <div className="panel-title">
          <h2>执行方式</h2>
          <span className="muted">互不自动切换</span>
        </div>
        <div className="execution-modes">
          <article>
            <strong>历史查看</strong>
            <p>读取已有运行、参数和答案，不执行模型或工具。</p>
            <button
              className="quiet"
              disabled={!source}
              onClick={() => onRun(source)}
            >
              打开来源运行
            </button>
          </article>
          <article>
            <strong>录制结果重跑</strong>
            <p>
              调用模型，只使用录制结果。新参数或调用超出录制时停止为
              replay_mismatch。
            </p>
            <select
              aria-label="录制选择"
              value={recording}
              onChange={(e) => {
                setRecording(e.target.value);
                const r = recordings.find(
                  (r) => r.recording_id === e.target.value,
                );
                if (r) setSource(r.source_run_id);
              }}
            >
              {recordings.map((r) => (
                <option value={r.recording_id} key={r.recording_id}>
                  {r.recording_id.slice(0, 8)} · {r.tool_calls} 次工具
                </option>
              ))}
            </select>
            <button
              className="quiet"
              disabled={busy || !recording}
              onClick={() =>
                act(`/recordings/${recording}/replay`, {
                  model: model.trim() || null,
                })
              }
            >
              调用模型重跑录制
            </button>
          </article>
          <article>
            <strong>冻结场景评测</strong>
            <p>
              调用模型，允许新查询。工具读取已冻结的 PostgreSQL 与向量副本。
            </p>
            <select
              aria-label="冻结场景选择"
              value={scenario}
              onChange={(e) => {
                setScenario(e.target.value);
                const selected = scenarios.find(
                  (s) => s.scenario_id === e.target.value,
                );
                if (selected?.source_run_id) setSource(selected.source_run_id);
              }}
            >
              {scenarios.map((s) => (
                <option value={s.scenario_id} key={s.scenario_id}>
                  {s.case_id} · {s.scenario_id.slice(0, 8)}
                </option>
              ))}
            </select>
            <button
              className="quiet"
              disabled={busy || !scenario}
              onClick={() =>
                act(`/scenarios/${scenario}/evaluate`, {
                  model: model.trim() || null,
                })
              }
            >
              调用模型评测冻结场景
            </button>
          </article>
        </div>
        <div className="evaluation-selectors">
          <label>
            来源运行
            <select
              aria-label="来源运行"
              value={source}
              onChange={(e) => setSource(e.target.value)}
            >
              {runs.map((r) => (
                <option key={r.run_id} value={r.run_id}>
                  {r.run_id.slice(0, 8)} · {r.status}
                </option>
              ))}
            </select>
          </label>
          <label>
            候选运行
            <select
              aria-label="候选运行"
              value={candidate}
              onChange={(e) => setCandidate(e.target.value)}
            >
              <option value="">选择候选</option>
              {runs
                .filter((r) => r.source_run_id)
                .map((r) => (
                  <option key={r.run_id} value={r.run_id}>
                    {r.run_id.slice(0, 8)} ·{" "}
                    {modes[r.execution_mode] || r.execution_mode} · {r.status}
                  </option>
                ))}
            </select>
          </label>
          <label>
            候选模型别名
            <input
              aria-label="候选模型别名"
              placeholder="留空沿用当前模型"
              maxLength={100}
              value={model}
              onChange={(e) => setModel(e.target.value)}
            />
          </label>
        </div>
        <div className="execution-actions">
          <button
            className="quiet"
            disabled={busy || !source}
            onClick={() => act(`/runs/${source}/recordings`, {})}
          >
            录制来源工具结果
          </button>
          <button
            className="quiet"
            disabled={busy || !source}
            onClick={() =>
              act("/scenarios", {
                case_id: "pool-exhaustion-01",
                source_run_id: source,
              })
            }
          >
            冻结 pool-exhaustion-01
          </button>
          {busy && <span className="muted">正在执行，请等待终止结果…</span>}
        </div>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
      </section>
      {comparison && (
        <section className="panel evaluation-panel">
          <div className="panel-title">
            <h2>执行差异</h2>
            <span className="muted">{modes[comparison.candidate_mode]}</span>
          </div>
          <div className="execution-summary">
            <span>
              Token 差值：
              {Object.values(comparison.usage.delta).reduce((a, b) => a + b, 0)}
            </span>
            <span>
              耗时差值：{comparison.duration_ms.delta?.toFixed(0) ?? "—"} ms
            </span>
            <span>
              候选规则：
              {comparison.evaluation
                ? comparison.evaluation.candidate.passed
                  ? "通过"
                  : "未通过"
                : "无关联标签"}
            </span>
          </div>
          <div className="evaluation-columns">
            {(["baseline", "candidate"] as const).map((side) => (
              <article key={side}>
                <h3>{side === "baseline" ? "来源" : "候选"}</h3>
                <button
                  className="quiet"
                  onClick={() => onRun(comparison[`${side}_run_id`])}
                >
                  打开{side === "baseline" ? "来源" : "候选"}记录
                </button>
                <h4>可观测事实</h4>
                {comparison.facts[side].length ? (
                  comparison.facts[side].map((fact, i) => (
                    <div className="failure-fact" key={i}>
                      <strong>{fact.code}</strong>
                      <pre>
                        {JSON.stringify(
                          fact.observed ?? fact.expected ?? {},
                          null,
                          2,
                        )}
                      </pre>
                      {[
                        ...(fact.location ? [fact.location] : []),
                        ...(fact.locations || []),
                      ].map((where, n) => (
                        <button
                          className="text-button"
                          key={n}
                          onClick={() =>
                            onRun(where.run_id, where.step_sequence)
                          }
                        >
                          定位{" "}
                          {where.step_sequence
                            ? `步骤 ${where.step_sequence} · `
                            : ""}
                          {where.field} ↗
                        </button>
                      ))}
                    </div>
                  ))
                ) : (
                  <p className="muted">
                    当前规则未发现上述失败事实，不代表所有质量问题均已排除。
                  </p>
                )}
                <h4>工具参数与调用次序</h4>
                <pre className="execution-json">
                  {JSON.stringify(comparison.tool_calls[side], null, 2)}
                </pre>
                <h4>最终答案</h4>
                <pre className="execution-json">
                  {JSON.stringify(comparison.answers[side], null, 2)}
                </pre>
              </article>
            ))}
          </div>
          <div className="execution-summary">
            新增引用：{comparison.citations.added.join(" · ") || "无"}
            <br />
            移除引用：{comparison.citations.removed.join(" · ") || "无"}
          </div>
        </section>
      )}
    </>
  );
}
import { authFetch as fetch } from "./auth";
