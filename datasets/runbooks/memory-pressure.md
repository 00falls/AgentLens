# inventory-api OOMKilled 与内存压力

## 核对容器内存限制

inventory-api 出现 OOMKilled、exitCode=137 时，对照 memory_working_set_mb、memory_limit_mb 与 container_restarts。工作集逼近容器限制并伴随重启，支持内存压力判断；137 单独出现也可能是其他 SIGKILL，不能只按退出码断定内存泄漏。

## 区分容量与泄漏

比较重启前增长趋势、请求体大小、缓存大小和堆转储。持续增长与突发大对象是不同路径；缺少堆证据时标注未知。扩容或调整内存上限应先评估节点剩余容量，不从一次 OOM 直接推荐无限扩容。
