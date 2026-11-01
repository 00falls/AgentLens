# payment-api 数据库连接被拒绝

## 区分 TCP 与 DNS

payment-api 报 ECONNREFUSED 或 connection refused 时，说明已尝试连接目标地址，但目标端口拒绝。核对数据库监听端口、地址与服务状态。它与 NXDOMAIN 的域名解析失败不同，也与 HikariPool 池内等待不同。

## 验证网络路径

在允许的网络诊断环境检查目标端口与实例健康，核对部署前后连接地址。不要未经证据将连接拒绝解释为密码错误；认证失败发生在不同连接阶段。
