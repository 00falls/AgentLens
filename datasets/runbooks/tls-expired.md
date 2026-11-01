# payment-api TLS 证书过期

## 识别握手失败

payment-api 调用外部服务出现 certificate has expired 或 CERT_HAS_EXPIRED 时，核对证书有效期、主机时钟与域名。TLS 握手发生在 HTTP 状态码之前，不能按普通 5xx 判断应用根因。

## 核验证书链

由授权操作人检查证书链、更新记录和实例差异。建议更新证书并验证，不建议关闭证书校验。输出只记录域名和有效期等非秘密信息。
