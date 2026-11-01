import { useEffect, useState } from "react";

type Experiment = {
  evaluation_id: string;
  name: string;
  dataset_name: string;
  summary: { selected: number; passed: number; failed: number; errors: number };
};
type Judge = {
  status: string;
  scores?: Record<
    string,
    { score: number; reason: string; evidence_ids: string[] }
  >;
};
type Difference = {
  case_id: string;
  change: string;
  baseline_outcome: string;
  candidate_outcome: string;
  baseline_run_id: string;
  candidate_run_id: string;
  baseline_checks: Record<string, boolean>;
  candidate_checks: Record<string, boolean>;
  baseline_dimensions: Record<string, boolean | null>;
  candidate_dimensions: Record<string, boolean | null>;
  improved_checks: string[];
  regressed_checks: string[];
  baseline_cause: string | null;
  candidate_cause: string | null;
  input_token_delta: number;
  output_token_delta: number;
  baseline_judge: Judge | null;
  candidate_judge: Judge | null;
};

const changes: Record<string, string> = {
  improved: "改善",
  regressed: "退步",
  mixed: "有增有减",
  unchanged: "未变",
  incomparable: "不可比较",
};

async function read<T>(
  url: string,
  project: string,
  signal: AbortSignal,
): Promise<T> {
  const response = await fetch(url, {
    headers: { "X-AgentLens-Project": project },
    signal,
  });
  if (!response.ok)
    throw new Error(
      `评测请求失败 (${response.status})：${await response.text()}`,
    );
  return response.json();
}

export function Evaluations({
  project,
  onRun,
}: {
  project: string;
  onRun: (id: string) => void;
}) {
  const [experiments, setExperiments] = useState<Experiment[]>([]);
  const [baseline, setBaseline] = useState("");
  const [candidate, setCandidate] = useState("");
  const [rows, setRows] = useState<Difference[]>([]);
  const [selected, setSelected] = useState<Difference | null>(null);
  const [filter, setFilter] = useState("all");
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    setExperiments([]);
    setRows([]);
    setSelected(null);
    setBaseline("");
    setCandidate("");
    setError("");
    read<{ evaluations: Experiment[] }>(
      "/evaluations",
      project,
      controller.signal,
    )
      .then((value) => {
        setExperiments(value.evaluations);
        setBaseline(value.evaluations[0]?.evaluation_id ?? "");
        setCandidate(value.evaluations.at(-1)?.evaluation_id ?? "");
      })
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => controller.abort();
  }, [project]);
  useEffect(() => {
    setRows([]);
    setSelected(null);
    setError("");
    if (!baseline || !candidate) return;
    const controller = new AbortController();
    const params = new URLSearchParams({ baseline, candidate });
    read<{ cases: Difference[] }>(
      `/evaluation-comparison?${params}`,
      project,
      controller.signal,
    )
      .then((value) => {
        setRows(value.cases);
        setSelected(value.cases[0] ?? null);
      })
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => controller.abort();
  }, [project, baseline, candidate]);
  const visible = rows.filter(
    (r) =>
      filter === "all" ||
      (filter === "failed" && r.candidate_outcome !== "passed") ||
      (filter === "changed" && r.change !== "unchanged"),
  );
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">EVALUATION LAB</p>
          <h1>
            把质量变化，落到每条证据<span>。</span>
          </h1>
          <p className="subtitle">
            逐例比较规则结果、诊断与 Judge 理由，回到原始执行定位问题。
          </p>
        </div>
      </div>
      <section className="panel evaluation-panel">
        <div className="panel-title">
          <h2>实验对比</h2>
          <span className="muted">当前项目范围 · 同一评测契约</span>
        </div>
        <div className="evaluation-selectors">
          <label>
            基线
            <select
              aria-label="基线实验"
              value={baseline}
              onChange={(e) => setBaseline(e.target.value)}
            >
              <option value="">选择实验</option>
              {experiments.map((e) => (
                <option key={e.evaluation_id} value={e.evaluation_id}>
                  {e.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            候选
            <select
              aria-label="候选实验"
              value={candidate}
              onChange={(e) => setCandidate(e.target.value)}
            >
              <option value="">选择实验</option>
              {experiments.map((e) => (
                <option key={e.evaluation_id} value={e.evaluation_id}>
                  {e.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            显示
            <select
              aria-label="评测结果筛选"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
            >
              <option value="all">全部用例</option>
              <option value="failed">候选未通过</option>
              <option value="changed">发生变化</option>
            </select>
          </label>
        </div>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        {!experiments.length && !error && (
          <p className="empty">当前项目暂无实验报告。</p>
        )}
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>用例</th>
                <th>基线</th>
                <th>候选</th>
                <th>变化</th>
                <th>Token 差值</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((row) => (
                <tr
                  key={row.case_id}
                  className={
                    selected?.case_id === row.case_id ? "selected" : ""
                  }
                  onClick={() => setSelected(row)}
                >
                  <td>{row.case_id}</td>
                  <td>{row.baseline_outcome}</td>
                  <td>{row.candidate_outcome}</td>
                  <td>{changes[row.change]}</td>
                  <td>
                    {row.input_token_delta + row.output_token_delta > 0
                      ? "+"
                      : ""}
                    {row.input_token_delta + row.output_token_delta}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!visible.length && rows.length > 0 && (
          <p className="empty">当前筛选没有匹配用例。</p>
        )}
      </section>
      {selected && (
        <section className="panel evaluation-panel">
          <div className="panel-title">
            <h2>{selected.case_id}</h2>
            <span className="muted">{changes[selected.change]}</span>
          </div>
          <div className="evaluation-columns">
            {(["baseline", "candidate"] as const).map((side) => (
              <article key={side}>
                <h3>{side === "baseline" ? "基线" : "候选"}</h3>
                <p className="evaluation-cause">
                  {selected[`${side}_cause`] ?? "执行未完成"}
                </p>
                <button
                  className="quiet"
                  onClick={() => onRun(selected[`${side}_run_id`])}
                >
                  打开{side === "baseline" ? "基线" : "候选"}运行 ↗
                </button>
                <div className="evaluation-checks">
                  {Object.entries(selected[`${side}_checks`]).map(
                    ([name, passed]) => (
                      <div key={name}>
                        <span>{name}</span>
                        <strong
                          className={passed ? "check-pass" : "check-fail"}
                        >
                          {passed ? "通过" : "失败"}
                        </strong>
                      </div>
                    ),
                  )}
                </div>
                <h4>独立结果维度</h4>
                <div className="evaluation-checks">
                  {Object.entries(selected[`${side}_dimensions`]).map(
                    ([name, passed]) => (
                      <div key={name}>
                        <span>{name}</span>
                        <strong>
                          {passed === null
                            ? "不适用"
                            : passed
                              ? "通过"
                              : "失败"}
                        </strong>
                      </div>
                    ),
                  )}
                </div>
                <h4>LLM Judge</h4>
                <p className="muted">未完成独立人工校准，分数仅供分析。</p>
                {selected[`${side}_judge`]?.status === "complete" ? (
                  Object.entries(selected[`${side}_judge`]!.scores!).map(
                    ([name, value]) => (
                      <details className="judge-criterion" key={name}>
                        <summary>
                          {name}
                          <strong>{value.score} / 2</strong>
                        </summary>
                        <p>{value.reason}</p>
                        <small>
                          {value.evidence_ids.join(" · ") || "无支持证据 ID"}
                        </small>
                      </details>
                    ),
                  )
                ) : (
                  <p className="muted">未评分或评分失败。</p>
                )}
              </article>
            ))}
          </div>
        </section>
      )}
    </>
  );
}
import { authFetch as fetch } from "./auth";
