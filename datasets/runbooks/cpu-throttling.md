# inventory-api CPU 配额节流

## 识别 CPU throttling

inventory-api 延迟升高时，对照 container_cpu_cfs_throttled_seconds_total、CPU limit 和队列。受 CPU 配额限制时，节点总体 CPU 仍可能空闲。不能只用 worker_cpu_percent 推断节点算力不足。

## 继续定位

比较发布前后单位请求 CPU、请求量与热点堆栈。区分流量增长和代码回归后再建议调整配额。内存与 CPU 指标需要分别判断，不把所有资源故障混为一类。
