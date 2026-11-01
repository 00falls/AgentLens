# inventory-api 消费积压

## 区分消费积压与 HTTP 队列

inventory-api 消费者 lag、oldest_message_age 上升时，对照生产速率、消费速率与失败重试。消息积压与 HTTP Worker queue full 有相似表现，但需要使用对应队列的指标与组件日志。

## 核对消费故障

检查消费者存活、分区分配、处理时长与毒消息。增加消费者之前确认分区数与下游容量，避免把积压转成数据库过载。
