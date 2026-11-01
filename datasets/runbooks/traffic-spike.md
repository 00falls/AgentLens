# inventory-api 流量突增与队列饱和

## 识别过载

inventory-api 的 Worker queue full、HTTP 503 与 queue_length 上升时，对比 request_rate、baseline_request_rate 和 worker_cpu_percent。流量显著超过基线且队列与 CPU 同时饱和，支持处理能力不足。

## 确定流量来源

按调用方、路径和时间统计流量，排查批处理、热点请求或重试放大。没有来源证据不能断言攻击。可建议限流与扩容评估，但需要确认业务优先级、丢弃策略和节点容量。
