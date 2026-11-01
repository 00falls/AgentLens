# order-api HTTP 客户端连接池等待

## 区分两种连接池

order-api 的 HTTP client pool lease timeout、pending acquire 与外部 HTTP 请求有关；HikariPool connection acquisition 属于数据库连接池。两种池都可能产生请求排队，应依据日志组件名与具体指标区分。

## 检查下游与连接释放

核对 HTTP 连接上限、下游响应耗时与响应体关闭情况。数据库 db_pool_active 不可用来证明 HTTP 池已满。保留发生等待的客户端名称与目标服务。
