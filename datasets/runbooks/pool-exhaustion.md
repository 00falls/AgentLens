# order-api 数据库连接池耗尽

## 识别连接获取等待

order-api 使用 HikariPool。connection acquisition timed out 表示等待池内连接超时，不等于 SQL 执行超时。对照 db_pool_active、db_pool_max、db_pool_waiters；active 达到 max、idle=0 且 waiters 持续上升时，可判断连接池饱和。结合相同时间窗的 5xx，确认影响范围。

## 继续调查与变更条件

区分慢查询、长事务与未释放连接，需要连接持有时长、数据库会话、锁等待和调用栈。仅凭池满不能认定连接泄漏。记录数据库剩余连接容量，再评估限流、回滚或调整池大小；未经容量验证不要直接扩大 max。任何生产变更都需要操作人审批。
