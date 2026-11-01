import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";
import { Evaluations } from "./evaluations";
import { Replays } from "./replays";
import { AuthGate, authFetch as fetch } from "./auth";
import { Operations } from "./operations";

type Status =
  | "running"
  | "diagnosed"
  | "insufficient_evidence"
  | "interrupted"
  | "failed"
  | "cancelled"
  | "replay_mismatch";
type Usage = { input_tokens: number; output_tokens: number };
type Run = {
  execution_mode: string;
  run_id: string;
  thread_id: string | null;
  project_id: string;
  status: Status;
  input: string;
  trace_id: string | null;
  started_at: string;
  duration_ms: number | null;
  usage: Usage;
};
type Step = {
  sequence: number;
  kind: string;
  name: string;
  input: Record<string, unknown>;
  output: Record<string, unknown> | null;
  error: string | null;
  duration_ms: number;
  span_id: string | null;
};
type Detail = Run & {
  output: {
    cause_summary: string;
    evidence_ids: string[];
    unknowns: string[];
    next_steps: string[];
  } | null;
  error: string | null;
  steps: Step[];
  checkpoint_id: string | null;
  source_run_id: string | null;
  versions: Record<string, unknown>;
  finished_at: string | null;
};
type Span = {
  span_id: string;
  parent_span_id: string | null;
  name: string;
  kind: string;
  start_ns: string;
  end_ns: string;
  duration_ms: number;
  status: string;
  attributes: Record<string, unknown>;
  resource: Record<string, unknown>;
  scope: string;
};
type Trace = {
  trace_id: string;
  spans: Span[];
  request_span_received: boolean;
  business_finished: boolean;
};
const statusText: Record<Status, string> = {
  running: "执行中",
  diagnosed: "已诊断",
  insufficient_evidence: "证据不足",
  interrupted: "待确认",
  failed: "失败",
  cancelled: "已取消",
  replay_mismatch: "录制不匹配",
};
const initial = new URLSearchParams(location.search);
const time = (value: string) =>
  new Date(value).toLocaleString("zh-CN", {
    hour12: false,
    timeZone: "Asia/Shanghai",
  });
const ms = (value: number | null) =>
  value === null
    ? "执行中"
    : value >= 1000
      ? `${(value / 1000).toFixed(2)} s`
      : `${value.toFixed(1)} ms`;
const short = (value: string | null) => (value ? value.slice(0, 8) : "—");

async function get<T>(
  path: string,
  project: string,
  signal: AbortSignal,
): Promise<T> {
  const response = await fetch(path, {
    headers: { "X-AgentLens-Project": project },
    signal,
  });
  if (!response.ok)
    throw new Error(`请求失败 (${response.status})：${await response.text()}`);
  return response.json();
}

function Badge({ status }: { status: Status }) {
  return (
    <span className={`badge ${status}`}>
      <i />
      {statusText[status]}
    </span>
  );
}

function Icon({ name }: { name: "runs" | "trace" | "refresh" | "arrow" }) {
  const shapes = {
    runs: (
      <>
        <rect x="4" y="4" width="16" height="16" rx="3" />
        <path d="M8 9h8M8 13h8M8 17h4" />
      </>
    ),
    trace: (
      <>
        <circle cx="6" cy="5" r="2" />
        <circle cx="18" cy="12" r="2" />
        <circle cx="6" cy="19" r="2" />
        <path d="M6 7v10M8 5h3v7h5" />
      </>
    ),
    refresh: (
      <>
        <path d="M19 8a7 7 0 1 0 0 8M19 3v5h-5" />
      </>
    ),
    arrow: (
      <>
        <path d="m9 5 7 7-7 7" />
      </>
    ),
  };
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {shapes[name]}
    </svg>
  );
}

function TraceView({
  value,
  error,
  onRefresh,
}: {
  value: Trace | null;
  error: string;
  onRefresh: () => void;
}) {
  const [selected, setSelected] = useState<Span | null>(null);
  const spans = value?.spans ?? [];
  const map = new Map(spans.map((span) => [span.span_id, span]));
  const start = spans.length
    ? spans.reduce(
        (a, s) => (BigInt(s.start_ns) < a ? BigInt(s.start_ns) : a),
        BigInt(spans[0].start_ns),
      )
    : 0n;
  const end = spans.reduce(
    (a, s) => (BigInt(s.end_ns) > a ? BigInt(s.end_ns) : a),
    start + 1n,
  );
  const roots = spans.filter(
    (span) => !span.parent_span_id || !map.has(span.parent_span_id),
  );
  const ordered: { span: Span; depth: number }[] = [];
  const visited = new Set<string>();
  function visit(span: Span, depth: number) {
    if (visited.has(span.span_id)) return;
    visited.add(span.span_id);
    ordered.push({ span, depth });
    spans
      .filter((child) => child.parent_span_id === span.span_id)
      .forEach((child) => visit(child, depth + 1));
  }
  roots.forEach((root) => visit(root, 0));
  spans
    .filter((span) => !visited.has(span.span_id))
    .forEach((span) => visit(span, 0));
  return (
    <section className="trace-view">
      <div className="section-heading">
        <div>
          <h3>分布式调用链</h3>
          <p>异步接收 · 已收到 {spans.length} 个 Span，后续片段可继续到达</p>
        </div>
        <button className="quiet" onClick={onRefresh}>
          <Icon name="refresh" />
          刷新调用链
        </button>
      </div>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {!value && !error && <p className="empty">正在读取调用链…</p>}
      {value && !spans.length && (
        <p className="empty">
          尚未接收到关联 Span。业务结果已单独保存，可稍后刷新。
        </p>
      )}
      {!!spans.length && (
        <div className="waterfall">
          <div className="waterfall-head">
            <span>操作 / 服务</span>
            <span>持续时间与层级</span>
          </div>
          {ordered.map(({ span, depth }) => (
            <button
              className={`span-row ${selected?.span_id === span.span_id ? "chosen" : ""}`}
              key={span.span_id}
              onClick={() => setSelected(span)}
            >
              <span
                className="span-name"
                style={{ paddingLeft: 16 + depth * 16 }}
              >
                <i
                  className={
                    span.status === "STATUS_CODE_ERROR"
                      ? "dot error-dot"
                      : "dot"
                  }
                />
                <span>
                  <strong>{span.name}</strong>
                  <small>{String(span.resource["service.name"] ?? "")}</small>
                </span>
              </span>
              <span className="span-track">
                <i
                  className={
                    span.status === "STATUS_CODE_ERROR"
                      ? "bar error-bar"
                      : "bar"
                  }
                  style={{
                    marginLeft: `${(Number(BigInt(span.start_ns) - start) / Number(end - start)) * 75}%`,
                    width: `${Math.max(0.7, (Number(BigInt(span.end_ns) - BigInt(span.start_ns)) / Number(end - start)) * 75)}%`,
                  }}
                />
                <small>{ms(span.duration_ms)}</small>
              </span>
            </button>
          ))}
        </div>
      )}
      {selected && (
        <div className="span-inspector">
          <div className="section-heading">
            <h3>{selected.name}</h3>
            <span className="mono muted">{selected.span_id}</span>
          </div>
          <p className="muted">
            {selected.kind} · {selected.scope} · {selected.status}
          </p>
          <pre>{JSON.stringify(selected.attributes, null, 2)}</pre>
        </div>
      )}
    </section>
  );
}

function App({ authorizedProject, logout }: { authorizedProject: string; logout: () => void }) {
  const [view, setView] = useState(
    ["evaluations", "replays", "operations"].includes(initial.get("view") || "")
      ? initial.get("view")!
      : "runs",
  );
  const [project, setProject] = useState(
    authorizedProject,
  );
  const [status, setStatus] = useState("");
  const [threadInput, setThreadInput] = useState("");
  const [thread, setThread] = useState("");
  const [offset, setOffset] = useState(0);
  const [list, setList] = useState<{ total: number; runs: Run[] } | null>(null);
  const [runId, setRunId] = useState<string | null>(initial.get("run"));
  const [detail, setDetail] = useState<Detail | null>(null);
  const [tab, setTab] = useState(
    initial.get("tab") === "trace" ? "trace" : "overview",
  );
  const [trace, setTrace] = useState<Trace | null>(null);
  const [listError, setListError] = useState("");
  const [detailError, setDetailError] = useState("");
  const [traceError, setTraceError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [focusedStep, setFocusedStep] = useState<number | null>(null);
  const [pendingStep, setPendingStep] = useState<number | null>(null);
  useEffect(() => {
    if (pendingStep !== null && detail?.run_id === runId) {
      setFocusedStep(pendingStep);
      setTab("steps");
      setPendingStep(null);
    }
  }, [detail, runId, pendingStep]);
  useEffect(() => {
    const params = new URLSearchParams(location.search);
    params.set("view", view);
    history.replaceState(null, "", `?${params}`);
  }, [view]);
  useEffect(() => {
    const controller = new AbortController();
    setListError("");
    setList(null);
    const params = new URLSearchParams({ limit: "8", offset: String(offset) });
    if (status) params.set("status", status);
    if (thread) params.set("thread_id", thread);
    get<{ total: number; runs: Run[] }>(
      `/runs?${params}`,
      project,
      controller.signal,
    )
      .then(setList)
      .catch((error) => {
        if (error.name !== "AbortError") setListError(error.message);
      });
    return () => controller.abort();
  }, [project, status, thread, offset, refresh]);
  useEffect(() => {
    const params = new URLSearchParams({ project, view });
    if (runId) params.set("run", runId);
    params.set("tab", tab);
    history.replaceState(null, "", `?${params}`);
    setDetail(null);
    setDetailError("");
    setTrace(null);
    setFocusedStep(null);
    if (!runId) return;
    const controller = new AbortController();
    get<Detail>(`/runs/${runId}`, project, controller.signal)
      .then(setDetail)
      .catch((error) => {
        if (error.name !== "AbortError") setDetailError(error.message);
      });
    return () => controller.abort();
  }, [project, runId, refresh]);
  useEffect(() => {
    const params = new URLSearchParams(location.search);
    params.set("tab", tab);
    history.replaceState(null, "", `?${params}`);
    if (tab !== "trace" || !detail?.trace_id) return;
    const controller = new AbortController();
    setTraceError("");
    setTrace(null);
    get<Trace>(
      `/traces/${detail.trace_id}?run_id=${detail.run_id}`,
      project,
      controller.signal,
    )
      .then(setTrace)
      .catch((error) => {
        if (error.name !== "AbortError") setTraceError(error.message);
      });
    return () => controller.abort();
  }, [tab, detail, project]);
  function selectProject(value: string) {
    setProject(value);
    setRunId(null);
    setStatus("");
    setThread("");
    setThreadInput("");
    setOffset(0);
  }
  function cite(id: string) {
    const step = detail?.steps.find(
      (step) =>
        step.kind === "tool" &&
        step.output &&
        Object.values(step.output).some(
          (rows) =>
            Array.isArray(rows) && rows.some((row) => row.evidence_id === id),
        ),
    );
    setFocusedStep(step?.sequence ?? null);
    setTab("steps");
  }
  const rows = list?.runs ?? [];
  const pageTokens = rows.reduce(
    (sum, r) => sum + r.usage.input_tokens + r.usage.output_tokens,
    0,
  );
  return (
    <div className="shell">
      <aside className="sidebar">
        <a href="/workbench/" className="brand">
          <span className="brand-mark">
            a<span>l</span>
          </span>
          <div>
            AgentLens<small>OBSERVE · UNDERSTAND</small>
          </div>
        </a>
        <p className="nav-label">工作空间</p>
        <button className={`nav-item ${view === "operations" ? "active" : ""}`} onClick={() => setView("operations")}>用量与审计</button>
        <button
          className={`nav-item ${view === "runs" ? "active" : ""}`}
          onClick={() => {
            setView("runs");
            document
              .getElementById("run-list")
              ?.scrollIntoView({ behavior: "smooth" });
          }}
        >
          <Icon name="runs" />
          运行记录<span className="nav-count">{list?.total ?? "—"}</span>
        </button>
        <button
          className="nav-item"
          disabled={!detail?.trace_id}
          onClick={() => {
            setView("runs");
            setTab("trace");
            document
              .getElementById("run-detail")
              ?.scrollIntoView({ behavior: "smooth" });
          }}
        >
          <Icon name="trace" />
          当前调用链
        </button>
        <button
          className={`nav-item ${view === "evaluations" ? "active" : ""}`}
          onClick={() => {
            setView("evaluations");
            const params = new URLSearchParams(location.search);
            params.set("view", "evaluations");
            history.replaceState(null, "", `?${params}`);
          }}
        >
          <Icon name="runs" />
          评测对比
        </button>
        <button
          className={`nav-item ${view === "replays" ? "active" : ""}`}
          onClick={() => setView("replays")}
        >
          <Icon name="refresh" />
          重跑与差异
        </button>
        <div className="sidebar-bottom">
          <span className="online-dot" /> 本地开发环境
          <p>
            合成运维场景
            <br />
            业务记录与观测数据独立保存
          </p>
          <a href="/docs" target="_blank" rel="noreferrer">
            API 文档 ↗
          </a>
        </div>
      </aside>
      <div className="main-wrap">
        <header className="topbar">
          <span>
            运维排障 <span className="slash">/</span>{" "}
            <strong>执行工作台</strong>
          </span>
          <label className="project-picker">
            <span className="project-dot" />
            项目
            <select
              aria-label="选择项目"
              value={project}
              onChange={(event) => selectProject(event.target.value)}
            >
              <option value={authorizedProject}>{authorizedProject}</option>
            </select>
          </label>
          <button onClick={logout}>退出项目</button>
        </header>
        <main>
          {view === "operations" ? <Operations key={project} project={project} onRun={id => { setRunId(id); setView("runs"); }} /> : view === "evaluations" ? (
            <Evaluations
              key={project}
              project={project}
              onRun={(id) => {
                setRunId(id);
                setView("runs");
              }}
            />
          ) : view === "replays" ? (
            <Replays
              key={project}
              project={project}
              onRun={(id, sequence) => {
                setRunId(id);
                setView("runs");
                if (sequence !== undefined) setPendingStep(sequence);
              }}
            />
          ) : (
            <>
              <div className="page-heading">
                <div>
                  <p className="eyebrow">EXECUTION EXPLORER</p>
                  <h1>
                    让每一次决策，都有迹可循<span>。</span>
                  </h1>
                  <p className="subtitle">
                    从最终结论回到工具与证据，定位执行过程中发生了什么。
                  </p>
                </div>
                <button
                  onClick={() => setRefresh((value) => value + 1)}
                  className="refresh"
                >
                  <Icon name="refresh" />
                  刷新数据
                </button>
              </div>
              <section className="stats">
                <div>
                  <span>匹配的运行</span>
                  <strong>
                    {list?.total ?? "—"}
                    <small> 次</small>
                  </strong>
                  <p>当前项目及筛选范围</p>
                </div>
                <div>
                  <span>本页已诊断</span>
                  <strong>
                    {list
                      ? rows.filter((r) => r.status === "diagnosed").length
                      : "—"}
                    <small> / {rows.length}</small>
                  </strong>
                  <p>以业务运行状态为准</p>
                </div>
                <div>
                  <span>本页 Token</span>
                  <strong>{list ? pageTokens.toLocaleString() : "—"}</strong>
                  <p>模型输入与输出用量合计</p>
                </div>
                <div className="stat-accent">
                  <Icon name="trace" />
                  <span>关联调用链</span>
                  <strong>
                    {list ? rows.filter((r) => r.trace_id).length : "—"}
                    <small> / {rows.length}</small>
                  </strong>
                  <p>请求 · 模型 · 工具</p>
                </div>
              </section>
              <section className="panel" id="run-list">
                <div className="panel-title">
                  <div>
                    <h2>运行记录</h2>
                    <span className="muted">RUNS</span>
                  </div>
                  <span className="zone">北京时间 · UTC+8</span>
                </div>
                <form
                  className="filters"
                  onSubmit={(event) => {
                    event.preventDefault();
                    setThread(threadInput.trim());
                    setOffset(0);
                  }}
                >
                  <select
                    aria-label="运行状态"
                    value={status}
                    onChange={(event) => {
                      setStatus(event.target.value);
                      setOffset(0);
                    }}
                  >
                    <option value="">全部状态</option>
                    {Object.entries(statusText).map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                  <input
                    aria-label="按会话筛选"
                    placeholder="按完整会话 ID 筛选"
                    value={threadInput}
                    onChange={(event) => setThreadInput(event.target.value)}
                  />
                  <button type="submit" className="quiet">
                    筛选
                  </button>
                  {thread && (
                    <button
                      type="button"
                      className="text-button"
                      onClick={() => {
                        setThread("");
                        setThreadInput("");
                        setOffset(0);
                      }}
                    >
                      清除会话
                    </button>
                  )}
                </form>
                {listError && (
                  <p className="error" role="alert">
                    {listError}
                  </p>
                )}
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>运行 / 问题</th>
                        <th>状态</th>
                        <th>开始时间</th>
                        <th>耗时</th>
                        <th>Token</th>
                        <th>链路</th>
                        <th />
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((run) => (
                        <tr
                          key={run.run_id}
                          className={run.run_id === runId ? "selected" : ""}
                          onClick={() => setRunId(run.run_id)}
                        >
                          <td>
                            <button
                              className="run-link"
                              onClick={() => setRunId(run.run_id)}
                            >
                              <span className="mono">{short(run.run_id)}</span>
                              <span className="prompt-preview">
                                {run.input}
                              </span>
                            </button>
                          </td>
                          <td>
                            <Badge status={run.status} />
                            <small className="run-mode">
                              {(
                                {
                                  live: "现场",
                                  recorded_replay: "录制重跑",
                                  frozen_scenario: "冻结场景",
                                } as Record<string, string>
                              )[run.execution_mode] || run.execution_mode}
                            </small>
                          </td>
                          <td className="time-cell">{time(run.started_at)}</td>
                          <td className="mono">{ms(run.duration_ms)}</td>
                          <td className="mono">
                            {(
                              run.usage.input_tokens + run.usage.output_tokens
                            ).toLocaleString()}
                          </td>
                          <td>
                            <span
                              className={
                                run.trace_id ? "trace-indicator" : "muted"
                              }
                            >
                              {run.trace_id ? "已关联" : "—"}
                            </span>
                          </td>
                          <td>
                            <Icon name="arrow" />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {!list && !listError && <p className="empty">正在读取运行…</p>}
                {list && !rows.length && (
                  <p className="empty">
                    当前范围没有运行记录。可调整筛选，或通过 Agent API
                    创建一次调查。
                  </p>
                )}
                <div className="pagination">
                  <span>
                    {list
                      ? `共 ${list.total} 条，显示 ${rows.length ? offset + 1 : 0}–${offset + rows.length}`
                      : "正在加载"}
                  </span>
                  <div>
                    <button
                      disabled={!list || offset === 0}
                      onClick={() =>
                        setOffset((value) => Math.max(0, value - 8))
                      }
                    >
                      上一页
                    </button>
                    <button
                      disabled={!list || offset + 8 >= list.total}
                      onClick={() => setOffset((value) => value + 8)}
                    >
                      下一页
                    </button>
                  </div>
                </div>
              </section>
              <section className="panel detail-panel" id="run-detail">
                <div className="panel-title">
                  <div>
                    <h2>执行详情</h2>
                    <span className="mono muted">
                      {runId ? short(runId) : "选择一条运行"}
                    </span>
                  </div>
                  {detail && <Badge status={detail.status} />}
                </div>
                {detailError && (
                  <p className="error" role="alert">
                    {detailError}
                  </p>
                )}
                {!runId && (
                  <div className="detail-empty">
                    <Icon name="runs" />
                    <h3>从一次运行开始</h3>
                    <p>点击上方记录，查看诊断、工具结果和完整调用顺序。</p>
                  </div>
                )}
                {runId && !detail && !detailError && (
                  <p className="empty">正在读取执行详情…</p>
                )}
                {detail && (
                  <>
                    <div
                      className="tabs"
                      role="tablist"
                      aria-label="执行详情视图"
                    >
                      {[
                        ["overview", "诊断与证据"],
                        ["steps", `执行步骤 ${detail.steps.length}`],
                        ["trace", "调用链"],
                      ].map(([value, text]) => (
                        <button
                          role="tab"
                          aria-selected={tab === value}
                          className={tab === value ? "tab active" : "tab"}
                          key={value}
                          onClick={() => setTab(value)}
                        >
                          {value === "trace" && <Icon name="trace" />}
                          {text}
                        </button>
                      ))}
                    </div>
                    {tab === "overview" && (
                      <div className="overview">
                        <div className="question">
                          <span className="label">调查问题</span>
                          <p>{detail.input}</p>
                        </div>
                        {detail.error && (
                          <div className="error">
                            <strong>执行失败</strong>
                            <pre>{detail.error}</pre>
                          </div>
                        )}
                        {detail.output && (
                          <>
                            <div className="diagnosis">
                              <span className="label">诊断结论</span>
                              <h3>{detail.output.cause_summary}</h3>
                              <div className="citations">
                                {detail.output.evidence_ids.map((id) => (
                                  <button
                                    key={id}
                                    onClick={() => cite(id)}
                                    title="查看对应工具证据"
                                  >
                                    ↗ {id}
                                  </button>
                                ))}
                              </div>
                            </div>
                            <div className="findings">
                              <div>
                                <span className="label">尚未确认</span>
                                <ul>
                                  {detail.output.unknowns.map((item, index) => (
                                    <li key={index}>{item}</li>
                                  ))}
                                </ul>
                              </div>
                              <div>
                                <span className="label">建议检查</span>
                                <ol>
                                  {detail.output.next_steps.map(
                                    (item, index) => (
                                      <li key={index}>{item}</li>
                                    ),
                                  )}
                                </ol>
                              </div>
                            </div>
                          </>
                        )}
                        <dl className="metadata">
                          <div>
                            <dt>会话 ID</dt>
                            <dd className="mono">
                              <button
                                className="text-button mono"
                                onClick={() => {
                                  setThread(detail.thread_id ?? "");
                                  setThreadInput(detail.thread_id ?? "");
                                  setOffset(0);
                                }}
                              >
                                {detail.thread_id ?? "历史记录未关联"}
                              </button>
                            </dd>
                          </div>
                          <div>
                            <dt>Trace ID</dt>
                            <dd className="mono">
                              {detail.trace_id ?? "历史运行未采集"}
                            </dd>
                          </div>
                          <div>
                            <dt>Checkpoint ID</dt>
                            <dd className="mono">
                              {detail.checkpoint_id ?? "—"}
                            </dd>
                          </div>
                          <div>
                            <dt>模型用量</dt>
                            <dd>
                              {detail.usage.input_tokens.toLocaleString()} 输入
                              / {detail.usage.output_tokens.toLocaleString()}{" "}
                              输出
                            </dd>
                          </div>
                        </dl>
                        <details className="versions">
                          <summary>运行版本</summary>
                          <pre>{JSON.stringify(detail.versions, null, 2)}</pre>
                        </details>
                      </div>
                    )}
                    {tab === "steps" && (
                      <div className="steps">
                        {!detail.steps.length && (
                          <p className="empty">
                            本次调用没有模型或工具步骤（例如无模型确认恢复）。
                          </p>
                        )}
                        {detail.steps.map((step) => (
                          <details
                            className={`step ${step.error ? "step-error" : ""} ${focusedStep === step.sequence ? "focused" : ""}`}
                            open={focusedStep === step.sequence || undefined}
                            key={step.sequence}
                          >
                            <summary>
                              <span className="step-number">
                                {String(step.sequence).padStart(2, "0")}
                              </span>
                              <span className="step-icon">
                                <Icon
                                  name={step.kind === "tool" ? "runs" : "trace"}
                                />
                              </span>
                              <span className="step-title">
                                <strong>{step.name}</strong>
                                <small>
                                  {step.kind === "tool"
                                    ? "工具调用"
                                    : "模型调用"}
                                </small>
                              </span>
                              <span
                                className={
                                  step.error ? "failure-text" : "muted"
                                }
                              >
                                {step.error ? "错误" : "完成"}
                              </span>
                              <span className="mono muted">
                                {ms(step.duration_ms)}
                              </span>
                              <span className="expand">＋</span>
                            </summary>
                            <div className="step-content">
                              {step.error && (
                                <div className="error">
                                  <pre>{step.error}</pre>
                                </div>
                              )}
                              <div className="json-grid">
                                <div>
                                  <span className="label">输入参数</span>
                                  <pre>
                                    {JSON.stringify(step.input, null, 2)}
                                  </pre>
                                </div>
                                <div>
                                  <span className="label">返回结果</span>
                                  <pre>
                                    {JSON.stringify(step.output, null, 2)}
                                  </pre>
                                </div>
                              </div>
                              {step.span_id && (
                                <p className="mono muted">
                                  Span {step.span_id}
                                </p>
                              )}
                            </div>
                          </details>
                        ))}
                      </div>
                    )}
                    {tab === "trace" &&
                      (detail.trace_id ? (
                        <TraceView
                          key={detail.trace_id}
                          value={trace}
                          error={traceError}
                          onRefresh={() => setRefresh((value) => value + 1)}
                        />
                      ) : (
                        <p className="empty">
                          这条历史运行没有采集调用链；未根据业务记录伪造 Span。
                        </p>
                      ))}
                  </>
                )}
              </section>
              <footer>
                AgentLens <span>执行记录是事实依据 · 调用链用于观测</span>
                <span>合成数据 / 本地演示</span>
              </footer>
            </>
          )}
        </main>
      </div>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <AuthGate>{(project, logout) => <App key={project} authorizedProject={project} logout={logout} />}</AuthGate>
  </StrictMode>,
);
