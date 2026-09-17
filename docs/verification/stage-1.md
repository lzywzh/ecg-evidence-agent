# 阶段 1 验证记录

验证日期：2026-09-17
项目阶段：最小纵向链路
数据范围：仅项目自建合成文本

## 环境

- 操作系统：Windows 11，`Windows-11-10.0.26200-SP0`
- Python：3.13.13
- SQLite：3.51.2
- FastAPI：0.115.14
- Pydantic：2.9.2
- Uvicorn：0.30.6
- HTTPX：0.27.2

项目使用独立 `.venv`。实施时发现宽泛依赖范围会安装 FastAPI 0.141.1、Starlette 1.6.0 和 HTTPX 0.28.1，并产生测试客户端弃用警告；随后把依赖限制在已验证的兼容小版本范围，警告消失。当前测试输出无警告。

## 自动化测试

实际运行：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

实际结果：

```text
................................................................         [100%]
64 passed in 1.37s
```

退出状态为 0。外层 PowerShell 测得包含进程启动开销的总耗时约 2.04 秒。测试覆盖来源校验、事务回滚、SQL 元字符、三种格式解析、重复导入、关键词评分、证据不足、API 校验、脱敏错误和 CLI 退出码。

## CLI 与重启持久化

实际运行：

```powershell
$env:ECG_AGENT_DB_PATH = 'var/stage1-verification.db'
.\.venv\Scripts\python.exe -m ecg_evidence_agent init-db
.\.venv\Scripts\python.exe -m ecg_evidence_agent seed-synthetic
.\.venv\Scripts\python.exe -m ecg_evidence_agent seed-synthetic
```

三个独立 Python 进程的实际输出：

```json
{"status":"initialized"}
{"source_id":1,"document_id":1,"chunks_imported":4,"created":true}
{"source_id":1,"document_id":1,"chunks_imported":4,"created":false}
```

这证明数据库在进程结束后仍然存在，并且相同来源与相同文件的第二次导入不会新增片段。

## API 冒烟验证

实际启动命令：

```powershell
$env:ECG_AGENT_DB_PATH = 'var/stage1-verification.db'
.\.venv\Scripts\python.exe -m uvicorn ecg_evidence_agent.api.app:app --host 127.0.0.1 --port 8000
```

Uvicorn 成功启动，三个 HTTP 请求均返回 200。

健康检查实际响应：

```json
{
  "status": "ok",
  "database": "ok"
}
```

查询 `QTc` 的实际命中：

```json
{
  "query": "QTc",
  "retrieval_method": "keyword-v1",
  "status": "found",
  "hits": [
    {
      "chunk_id": 3,
      "text": "# QTc\n\n在本合成样例中，检索词“QTc”对应测试代号 field-qtc。QT 与 QTc 使用不同代号，用于验证系统不会把两个字符串无条件视为相同字段。",
      "score": 4.3,
      "locator": "heading:QTc@line:9",
      "source_id": 1,
      "source_key": "synthetic.ecg-terms.v1",
      "institution": "合成数据实验室",
      "title": "合成心电术语检索样例",
      "version": "1.0",
      "published_date": "2026-09-17",
      "source_uri": "data/synthetic/terminology.md",
      "scope": "仅用于测试检索、引用和缺失证据处理，不表达医学定义",
      "is_synthetic": true
    }
  ]
}
```

查询 `资料中不存在的合成词乙` 的实际响应：

```json
{
  "query": "资料中不存在的合成词乙",
  "retrieval_method": "keyword-v1",
  "status": "insufficient_evidence",
  "hits": []
}
```

请求结束后使用 Ctrl+C 正常关闭 Uvicorn，应用完成关闭流程。

## 一个可复现的失败行为

创建一个内容为非法 UTF-8 字节 `0xFF` 的 `.txt` 文件并调用解析器：

```python
path.write_bytes(b"\xff")
load_and_parse(path)
```

系统抛出 `DocumentImportError("document is not valid UTF-8")`，不会把损坏文本写入数据库。自动化测试 `test_rejects_invalid_utf8` 固定了这一行为。

## 已知限制

- 尚未导入或验证真实医学资料。
- 尚未实现 PDF、OCR、语义检索、字段提取、模型回答和工具调用。
- 尚未进行并发负载、长时间运行、容器和公开部署验证。
- `keyword-v1` 根据字符串匹配排序，不能理解医学语义；词汇相似不等于证据支持。
- 当前语料与测试集规模只能证明程序行为，不能报告临床准确率或真实检索效果。
