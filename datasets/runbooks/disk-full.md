# inventory-api 磁盘空间不足

## 识别写入失败

inventory-api 出现 ENOSPC、No space left on device 时，对照磁盘使用率与 inode 数。磁盘字节未满仍可能 inode 耗尽；它与内存 OOMKilled 是不同资源问题。

## 定位增长来源

区分日志、临时文件与业务数据目录，检查挂载卷与保留策略。删除数据前由操作人确认保留要求，本助手只列出待检查目录与证据，不自动清理。
