# 心电术语与证据检索教学项目

这是一个用于学习 Python 后端、资料持久化、可解释检索和证据追踪的教学项目。阶段 1 只处理项目自带的合成文本，不包含真实患者信息，不是医疗器械，也不提供诊断、治疗、用药或风险决策。

## 阶段 1 已实现

- 导入 UTF-8 编码的 TXT、Markdown 和结构化 JSON。
- 保存来源、文档和片段到 SQLite，重启后仍可查询。
- 使用文件 SHA-256 保证同一来源下重复导入幂等。
- 检查来源标识冲突，避免静默覆盖版本或许可信息。
- 使用确定性的 `keyword-v1` 关键词评分返回 Top-k 原文片段。
- 每个命中都带来源机构、标题、版本、日期、位置和合成标记。
- 没有命中时返回 `insufficient_evidence`，不生成答案。
- 提供 CLI、FastAPI、64 个自动化测试和端到端验证记录。

## 尚未实现

- 真实指南资料导入与专业医学核验。
- PDF、OCR、原始心电波形或真实患者数据处理。
- 报告字段提取、语义检索、模型回答和工具调用。
- 并发负载测试、容器化和公开部署。

## 环境与依赖

- Python 3.11 或更高版本；本机已用 Python 3.13.13 验证。
- FastAPI：定义 HTTP 接口和错误边界。
- Pydantic：校验来源、查询和响应结构。
- Uvicorn：本地运行 ASGI 应用。
- SQLite：通过 Python 标准库 `sqlite3` 持久化，不引入 ORM。
- pytest、HTTPX：开发和 API 测试依赖。

这些依赖均为当前 Python Web 生态中的常用维护项目。第一阶段不用 SQLAlchemy、向量数据库或 Agent 框架，因为标准库 SQLite 和普通 Python 已足以验证核心数据流。

在 PowerShell 中创建独立环境：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

不要把真实密钥写入代码或 `.env`。阶段 1 不需要 API Key。

## 最快演示

初始化数据库并导入项目自带合成资料：

```powershell
$env:ECG_AGENT_DB_PATH = 'var/demo.db'
.\.venv\Scripts\python.exe -m ecg_evidence_agent init-db
.\.venv\Scripts\python.exe -m ecg_evidence_agent seed-synthetic
```

第二次运行 `seed-synthetic` 会返回 `created=false`，不会重复写入片段。

启动 API：

```powershell
$env:ECG_AGENT_DB_PATH = 'var/demo.db'
.\.venv\Scripts\python.exe -m uvicorn ecg_evidence_agent.api.app:app --host 127.0.0.1 --port 8000
```

在另一个 PowerShell 终端查询：

```powershell
$body = @{ query = 'QTc'; top_k = 3 } | ConvertTo-Json
Invoke-RestMethod `
  -Method Post `
  -Uri 'http://127.0.0.1:8000/v1/evidence/search' `
  -ContentType 'application/json' `
  -Body $body
```

命中响应的关键结构：

```json
{
  "query": "QTc",
  "retrieval_method": "keyword-v1",
  "status": "found",
  "hits": [
    {
      "text": "合成资料原文",
      "locator": "heading:QTc@line:9",
      "source_key": "synthetic.ecg-terms.v1",
      "is_synthetic": true
    }
  ]
}
```

证据不足响应：

```json
{
  "query": "资料中不存在的词",
  "retrieval_method": "keyword-v1",
  "status": "insufficient_evidence",
  "hits": []
}
```

健康检查：

```powershell
Invoke-RestMethod -Uri 'http://127.0.0.1:8000/health'
```

未初始化数据库时健康检查返回脱敏的 503，不会在导入 API 模块时自动创建文件。

## 导入自定义本地文本

来源清单采用 JSON。真实来源需要 HTTP(S) `source_uri`；无法确认的版本或发布日期保留为 `null`，不能用获取日期代替发布日期。

```json
{
  "source_key": "synthetic.example.v1",
  "institution": "合成数据实验室",
  "title": "合成检索样例",
  "source_type": "synthetic",
  "version": "1.0",
  "published_date": "2026-09-17",
  "source_uri": "data/example.md",
  "retrieved_at": "2026-09-17",
  "scope": "仅用于软件流程测试",
  "usage_terms": "自建合成数据，可用于教学",
  "redistributable": true,
  "is_synthetic": true
}
```

执行导入：

```powershell
$env:ECG_AGENT_DB_PATH = 'var/demo.db'
.\.venv\Scripts\python.exe -m ecg_evidence_agent import `
  --manifest .\data\source.json `
  --file .\data\example.md
```

支持格式：

- TXT：连续非空行组成片段，位置保存为行号范围。
- Markdown：ATX 标题形成片段，位置保存标题和行号。
- JSON：结构必须为 `{"sections":[{"locator":"...","text":"..."}]}`，额外字段会被拒绝。

## `keyword-v1` 如何工作

1. 使用 Unicode NFKC、大小写折叠和空白归一化处理查询与正文。
2. 拉丁字母和数字按完整 token 匹配，因此查询 `QT` 不会自动命中 `QTc`。
3. 连续中文字符使用子串匹配。
4. 得分由完整短语奖励、查询词覆盖率和封顶词频组成。
5. 同分时按来源、片段顺序和片段 ID 稳定排序。

该算法可解释、可重复，但不理解医学语义。中文近义表达、跨语言表达或词汇不同的相关证据可能无法命中；词汇相似也不代表医学含义相同。是否增加 FTS5 或语义检索，必须由阶段 2 的固定评测结果决定。

## 数据流

1. CLI 读取来源清单和用户明确指定的本地文件。
2. Pydantic 校验来源字段、合成标记和真实来源 URL。
3. 解析器生成带原文位置的片段，导入服务计算文件哈希。
4. SQLite 存储在一个事务中写入来源、文档和全部片段。
5. API 校验查询后，从 SQLite 读取候选片段。
6. `keyword-v1` 评分并稳定排序，服务层绑定来源元数据。
7. API 返回证据原文，或明确返回 `insufficient_evidence`。

## 项目结构

```text
src/ecg_evidence_agent/
├─ domain/       # 数据模型与接口契约
├─ ingestion/    # 文本解析与导入编排
├─ storage/      # SQLite 表结构、事务和查询
├─ retrieval/    # 确定性关键词评分
├─ services/     # 业务用例
├─ api/          # FastAPI 边界
├─ cli.py        # 本地命令入口
└─ config.py     # 环境配置
```

## 运行测试

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

测试只使用临时目录和合成数据，不联网、不调用模型，也不读写个人资料。实际验证证据见 [阶段 1 验证记录](docs/verification/stage-1.md)。

## 数据、许可与隐私边界

- 项目自带内容全部标记为合成数据，不是指南摘录或医学定义。
- 不要把实际患者资料放入仓库、测试、日志或外部模型。
- 导入真实资料前必须核实机构、标题、版本、适用范围和使用条件。
- 如果资料不能再分发，只保存元数据和本地导入说明，不提交原文。
- 文档中的“忽略规则”“调用工具”等文字只作为待检索数据，不能改变程序行为。
- 没有专业人员核验时，只能描述为“相对指定资料的检索与引用一致性”，不能称为临床准确率。
