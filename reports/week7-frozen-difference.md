# 执行差异

来源：302c48a7-9420-4b60-9ee6-477f6da3e6f0
候选：7d81edc0-496d-42ee-a739-77c0d98f2bd1
模式：frozen_scenario

重跑调用模型；不宣称确定性复现。

| 工具 | 来源次数 | 候选次数 |
|---|---:|---:|
| query_metrics | 2 | 1 |
| search_experiences | 1 | 1 |
| search_logs | 2 | 1 |
| search_runbooks | 1 | 1 |

## 可观测事实

```json
{
  "baseline": [
    {
      "code": "labelled_relevant_chunks_not_retrieved",
      "expected": [
        "pool-exhaustion--s01",
        "pool-exhaustion--s02"
      ],
      "observed": [
        "healthy--s02",
        "healthy--s01",
        "db-lock-wait--s01",
        "downstream-timeout--s02",
        "downstream-timeout--s01"
      ],
      "locations": [
        {
          "run_id": "302c48a7-9420-4b60-9ee6-477f6da3e6f0",
          "step_sequence": 4,
          "field": "output.chunks"
        }
      ],
      "note": "This identifies a labelled miss, not its causal explanation."
    },
    {
      "code": "labelled_relevant_chunks_not_cited",
      "location": {
        "run_id": "302c48a7-9420-4b60-9ee6-477f6da3e6f0",
        "field": "output.evidence_ids"
      }
    }
  ],
  "candidate": []
}
```

## 参数、答案与引用

```json
{
  "tool_calls": {
    "baseline": [
      {
        "sequence": 2,
        "name": "search_logs",
        "arguments": {
          "service": "order-api",
          "start_time": "2026-10-30T14:00:00+08:00",
          "end_time": "2026-10-30T14:15:00+08:00",
          "level": "ERROR",
          "limit": 100
        },
        "normalized_arguments": {
          "service": "order-api",
          "start_time": "2026-10-30T06:00:00+00:00",
          "end_time": "2026-10-30T06:15:00+00:00",
          "level": "ERROR",
          "limit": 100
        },
        "error": null,
        "source_step_sequence": null,
        "key": "3f27c613646eda1e7dc6810d04c52f480b9688c6b3dd47553a2f00fd373df8c6"
      },
      {
        "sequence": 3,
        "name": "query_metrics",
        "arguments": {
          "service": "order-api",
          "start_time": "2026-10-30T14:00:00+08:00",
          "end_time": "2026-10-30T14:15:00+08:00",
          "limit": 100
        },
        "normalized_arguments": {
          "service": "order-api",
          "start_time": "2026-10-30T06:00:00+00:00",
          "end_time": "2026-10-30T06:15:00+00:00",
          "metric_name": null,
          "limit": 100
        },
        "error": null,
        "source_step_sequence": null,
        "key": "0a1ff9caf4d88b33b81efc403e5dd67fd774a9481e6e441f741c46074ce95bb7"
      },
      {
        "sequence": 4,
        "name": "search_runbooks",
        "arguments": {
          "query": "order-api 服务异常 错误日志 排查",
          "top_k": 5
        },
        "normalized_arguments": {
          "query": "order-api 服务异常 错误日志 排查",
          "top_k": 5
        },
        "error": null,
        "source_step_sequence": null,
        "key": "0ff83778510c40d808e4beb30107fec85dbbe8f152149abef85146e18ce95513"
      },
      {
        "sequence": 6,
        "name": "search_logs",
        "arguments": {
          "end_time": "2026-10-30T14:15:00+08:00",
          "level": "WARN",
          "limit": 100,
          "service": "order-api",
          "start_time": "2026-10-30T14:00:00+08:00"
        },
        "normalized_arguments": {
          "service": "order-api",
          "start_time": "2026-10-30T06:00:00+00:00",
          "end_time": "2026-10-30T06:15:00+00:00",
          "level": "WARN",
          "limit": 100
        },
        "error": null,
        "source_step_sequence": null,
        "key": "9b186b7752340513aadd3659f7b0c5133952fd086d8200f575a5bd710497b772"
      },
      {
        "sequence": 7,
        "name": "query_metrics",
        "arguments": {
          "end_time": "2026-10-30T14:15:00+08:00",
          "limit": 100,
          "service": "order-api",
          "start_time": "2026-10-30T14:00:00+08:00"
        },
        "normalized_arguments": {
          "service": "order-api",
          "start_time": "2026-10-30T06:00:00+00:00",
          "end_time": "2026-10-30T06:15:00+00:00",
          "metric_name": null,
          "limit": 100
        },
        "error": null,
        "source_step_sequence": null,
        "key": "0a1ff9caf4d88b33b81efc403e5dd67fd774a9481e6e441f741c46074ce95bb7"
      },
      {
        "sequence": 8,
        "name": "search_experiences",
        "arguments": {
          "service": "order-api",
          "limit": 5
        },
        "normalized_arguments": {
          "service": "order-api",
          "limit": 5
        },
        "error": null,
        "source_step_sequence": null,
        "key": "c815609630b1f516b633bb3d6ef177270460779f280562f2e2b210aec69f0a0b"
      }
    ],
    "candidate": [
      {
        "sequence": 2,
        "name": "search_logs",
        "arguments": {
          "service": "order-api",
          "start_time": "2026-10-30T14:00:00+08:00",
          "end_time": "2026-10-30T14:15:00+08:00",
          "level": "ERROR",
          "limit": 100
        },
        "normalized_arguments": {
          "service": "order-api",
          "start_time": "2026-10-30T06:00:00+00:00",
          "end_time": "2026-10-30T06:15:00+00:00",
          "level": "ERROR",
          "limit": 100
        },
        "error": null,
        "source_step_sequence": null,
        "key": "3f27c613646eda1e7dc6810d04c52f480b9688c6b3dd47553a2f00fd373df8c6"
      },
      {
        "sequence": 3,
        "name": "query_metrics",
        "arguments": {
          "service": "order-api",
          "start_time": "2026-10-30T14:00:00+08:00",
          "end_time": "2026-10-30T14:15:00+08:00",
          "limit": 100
        },
        "normalized_arguments": {
          "service": "order-api",
          "start_time": "2026-10-30T06:00:00+00:00",
          "end_time": "2026-10-30T06:15:00+00:00",
          "metric_name": null,
          "limit": 100
        },
        "error": null,
        "source_step_sequence": null,
        "key": "0a1ff9caf4d88b33b81efc403e5dd67fd774a9481e6e441f741c46074ce95bb7"
      },
      {
        "sequence": 5,
        "name": "search_runbooks",
        "arguments": {
          "query": "HikariPool connection acquisition timed out; db_pool_active 达到 db_pool_max, db_pool_waiters 高, http_5xx_ratio 上升",
          "top_k": 5
        },
        "normalized_arguments": {
          "query": "HikariPool connection acquisition timed out; db_pool_active 达到 db_pool_max, db_pool_waiters 高, http_5xx_ratio 上升",
          "top_k": 5
        },
        "error": null,
        "source_step_sequence": null,
        "key": "6a569a564ca9dd2533527097cf88c2dc41a4436b9ba9e489f9dc3b517fba6ffd"
      },
      {
        "sequence": 6,
        "name": "search_experiences",
        "arguments": {
          "service": "order-api",
          "limit": 5
        },
        "normalized_arguments": {
          "service": "order-api",
          "limit": 5
        },
        "error": null,
        "source_step_sequence": null,
        "key": "c815609630b1f516b633bb3d6ef177270460779f280562f2e2b210aec69f0a0b"
      }
    ],
    "baseline_counts": {
      "search_logs": 2,
      "query_metrics": 2,
      "search_runbooks": 1,
      "search_experiences": 1
    },
    "candidate_counts": {
      "search_logs": 1,
      "query_metrics": 1,
      "search_runbooks": 1,
      "search_experiences": 1
    },
    "added": [
      {
        "key": "6a569a564ca9dd2533527097cf88c2dc41a4436b9ba9e489f9dc3b517fba6ffd",
        "count": 1
      }
    ],
    "removed": [
      {
        "key": "0a1ff9caf4d88b33b81efc403e5dd67fd774a9481e6e441f741c46074ce95bb7",
        "count": 1
      },
      {
        "key": "0ff83778510c40d808e4beb30107fec85dbbe8f152149abef85146e18ce95513",
        "count": 1
      },
      {
        "key": "9b186b7752340513aadd3659f7b0c5133952fd086d8200f575a5bd710497b772",
        "count": 1
      }
    ]
  },
  "answers": {
    "baseline": {
      "status": "diagnosed",
      "cause_summary": "在 2026-10-30 14:00–14:15（+08:00）窗口内，order-api 出现数据库连接池耗尽：14:02 的 ERROR 日志显示 HikariPool 获取连接超时 30000ms，active=20、idle=0、max=20；14:03 的指标显示 db_pool_active=20 已达到 db_pool_max=20，db_pool_waiters=48 个请求在排队，http_5xx_ratio 升至 0.38。日志与指标相互印证，说明连接池容量被占满、请求排队等待连接并超时，进而导致 5xx 比例升高。至于连接被长期占用的具体原因（慢 SQL、长事务、连接泄漏或下游数据库变慢），本次证据尚不能确定；手册 db-lock-wait--s01 也明确指出，只有池满日志无法确认锁为根因，需要 pg_stat_activity 的 wait_event_type=Lock 等数据佐证。本次未观察到 payment-api 超时相关日志或 payment_api_p95_ms 指标，因此下游超时路径（downstream-timeout--s01）暂无现场证据支持。",
      "evidence_ids": [
        "pool-exhaustion-log-1",
        "pool-exhaustion-metric-1",
        "pool-exhaustion-metric-2",
        "pool-exhaustion-metric-3",
        "pool-exhaustion-metric-4",
        "db-lock-wait--s01",
        "downstream-timeout--s01",
        "experience-40452d3e-6892-46e4-839d-a3ba9246c409"
      ],
      "unknowns": [
        "连接被长期占用的根因未证实：缺少慢查询日志、事务耗时、数据库侧会话状态与锁等待数据",
        "未确认是否存在连接泄漏（连接借出后未归还）",
        "未确认数据库实例自身是否出现性能退化或连接数上限限制",
        "未获取到 order-api 的请求量/QPS 与线程池指标，无法判断是流量突增还是连接持有时间变长",
        "WARN 级别日志在窗口内为空，无法从日志侧观察排队或重试过程",
        "历史经验 experience-40452d3e 为合成演示记录，其适用条件明确说明慢 SQL、泄漏等深层原因尚未确认，不能作为本次根因证据"
      ],
      "next_steps": [
        "按手册 db-lock-wait--s01：查询 14:00–14:15 窗口 pg_stat_activity 的 wait_event_type、事务年龄与阻塞关系，确认是否存在锁等待",
        "查询数据库侧慢查询日志与长事务，确认连接被长期占用的原因",
        "检查 order-api 连接借出/归还埋点与线程栈，排查连接泄漏或未关闭的 ResultSet/Statement",
        "对比该窗口前后的请求量（QPS）与平均响应时间，区分流量突增与连接持有时间变长",
        "检查 HikariCP 配置（maxPoolSize、connectionTimeout、leakDetectionThreshold）是否与当前负载匹配",
        "若怀疑下游影响，按手册 downstream-timeout--s01 获取 payment-api 同窗口日志与 payment_api_p95_ms 指标，对齐超时阈值与调用链",
        "临时缓解可考虑限流或扩容连接池，但需先确认数据库侧承载能力；本次未执行任何生产变更"
      ]
    },
    "candidate": {
      "status": "diagnosed",
      "cause_summary": "在 2026-10-30 14:00–14:15（+08:00）窗口内，order-api 出现数据库连接池饱和：14:02 日志报 HikariPool 获取连接超时 30000ms，active=20、idle=0、max=20；14:03 指标显示 db_pool_active=20 已达 db_pool_max=20，db_pool_waiters=48 个请求排队，http_5xx_ratio 升至 0.38。日志与指标相互印证，说明连接池容量被占满、请求排队等待连接超时，进而导致 5xx 比例升高。手册 pool-exhaustion--s01 指出 connection acquisition timed out 表示等待池内连接超时而非 SQL 执行超时，并建议对照 active/max/waiters 与同窗口 5xx 判断饱和与影响范围，与现场观察一致。连接被长期占用的具体原因（慢 SQL、长事务、连接泄漏或数据库变慢）本次证据尚不能确定；手册 db-lock-wait--s01 也提示仅凭池满日志无法确认锁为根因。",
      "evidence_ids": [
        "pool-exhaustion-log-1",
        "pool-exhaustion-metric-1",
        "pool-exhaustion-metric-2",
        "pool-exhaustion-metric-3",
        "pool-exhaustion-metric-4",
        "pool-exhaustion--s01",
        "db-lock-wait--s01",
        "experience-40452d3e-6892-46e4-839d-a3ba9246c409"
      ],
      "unknowns": [
        "连接被长期占用的根因未证实：缺少慢查询日志、事务耗时、数据库侧会话状态与锁等待数据",
        "未确认是否存在连接泄漏（连接借出后未归还）",
        "未确认数据库实例自身是否出现性能退化或连接数上限限制",
        "未获取 order-api 请求量/QPS 与线程池指标，无法区分流量突增与连接持有时间变长",
        "未获取 HTTP 客户端池相关指标，无法完全排除下游调用延迟的叠加影响（当前日志组件名为 HikariPool，指向数据库池）"
      ],
      "next_steps": [
        "按手册 pool-exhaustion--s01 复核 14:00–14:15 窗口的 db_pool_active/db_pool_max/db_pool_waiters 与 5xx 时间序列，确认饱和持续时长与影响范围",
        "查询数据库侧 pg_stat_activity 会话、wait_event_type=Lock、事务年龄与慢查询日志（14:00–14:15），验证是否存在长事务、锁等待或慢 SQL（参考 db-lock-wait--s01）",
        "检查 order-api 连接借出/归还埋点与线程栈，排查连接泄漏或未关闭的 ResultSet/Statement",
        "对比该窗口前后的请求量（QPS）与平均响应时间，区分流量突增与连接持有时间变长",
        "检查 HikariCP 配置（maxPoolSize、connectionTimeout、leakDetectionThreshold）是否与当前负载匹配",
        "临时缓解可考虑限流或扩容连接池，但需先确认数据库侧承载能力；本次未执行任何生产变更"
      ]
    }
  },
  "citations": {
    "added": [
      "pool-exhaustion--s01"
    ],
    "removed": [
      "downstream-timeout--s01"
    ]
  },
  "usage": {
    "baseline": {
      "input_tokens": 11812,
      "output_tokens": 1362
    },
    "candidate": {
      "input_tokens": 9001,
      "output_tokens": 1102
    },
    "delta": {
      "input_tokens": -2811,
      "output_tokens": -260
    }
  },
  "duration_ms": {
    "baseline": 16998.664999999997,
    "candidate": 13648.418,
    "delta": -3350.2469999999976
  }
}
```
