# order-api PostgreSQL 锁等待

## 识别阻塞事务

order-api SQL 延迟伴随 pg_stat_activity 的 wait_event_type=Lock 时，查询阻塞关系、事务年龄和等待语句。连接池 active 上升可能是锁等待的后果，只有池满日志无法确认锁为根因。

## 处理前记录证据

保留阻塞 PID、事务开始时间、涉及表与发布记录。终止事务可能回滚业务操作，需要操作人确认。对照慢查询与连接获取时间，分别标注数据库执行阶段与应用池等待阶段。
