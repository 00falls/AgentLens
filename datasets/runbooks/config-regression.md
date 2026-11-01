# payment-api 发布后数据库 DNS 配置错误

## 定位 NXDOMAIN

payment-api 发布后出现 NXDOMAIN、cannot be resolved 时，核对数据库主机名的拼写与配置来源。pg-paymnt.internal 与预期数据库域名不一致时，保留配置差异、发布时间和解析错误作为证据。NXDOMAIN 与连接拒绝是不同阶段的故障。

## 确认配置来源

检查 deployment 环境变量、配置文件与 DNS 记录的实际生效版本。多个实例是否一起失败有助区分配置回归与单实例缓存。向操作人建议回滚前，确认上一版本配置可用；本助手不修改部署。
