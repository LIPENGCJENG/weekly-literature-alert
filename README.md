# Weekly Literature Alert

这是一个用于每周自动检索、筛选并邮件推送文献的 Python 工作流，主题聚焦：

- 复合固态电解质
- 聚合物电解质
- 锂离子传导机理
- 陶瓷填料界面效应
- 聚合物-陶瓷界面与空间电荷层

工作流会从 OpenAlex、Crossref、Elsevier Scopus 和 Semantic Scholar 检索最近若干天的新论文，用 EasyScholar 查询 SCI 影响因子/JCR 分区，去重、评分、生成中文 Markdown/HTML 报告，并通过邮件发送。

## 项目结构

```text
weekly-literature-alert/
├── config.yaml
├── requirements.txt
├── README.md
├── src/
│   ├── main.py
│   ├── search_openalex.py
│   ├── search_crossref.py
│   ├── search_semantic_scholar.py
│   ├── search_elsevier.py
│   ├── rank_papers.py
│   ├── summarize_papers.py
│   └── send_email.py
├── data/
│   └── seen.json
├── reports/
│   └── weekly_report.md
├── tests/
└── .github/
    └── workflows/
        └── weekly-literature-alert.yml
```

## 安装依赖

```bash
cd weekly-literature-alert
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 配置 config.yaml

重点修改这些字段：

- `profile.email_to`：你的收件邮箱。本地运行时可写在这里，GitHub Actions 中建议用 `EMAIL_TO` Secret 覆盖。
- `search.days_back`：默认检索最近 30 天。
- `search.top_n`：每周推荐论文数量，默认 10。
- `search.min_recommendations`：当候选池足够时，至少推荐的论文数量，默认 5。
- `search.semantic_scholar_min_interval_seconds`：Semantic Scholar 请求间隔，默认 1.1 秒，用于满足每秒最多 1 次请求的限制。
- `keywords.include`：检索和相关性评分关键词。
- `keywords.exclude`：排除明显不相关主题。
- `venues.impact_factors`：期刊影响因子备用表。当 EasyScholar 未配置或查询失败时，评分会使用这里的数值。
- `ranking.weight_title_relevance` 和 `ranking.weight_impact_factor`：评分只由标题相关度和期刊影响因子组成。
- `easyscholar.min_interval_seconds`：EasyScholar 期刊指标查询间隔，避免请求过密。

## 本地运行

只生成报告、不发送邮件：

```bash
python src/main.py --dry-run
```

生成报告并尝试发送邮件：

```bash
python src/main.py
```

输出文件会保存在 `reports/`：

- `weekly_report.md`
- `weekly_report.html`
- `weekly_report_YYYY-MM-DD.md`
- `weekly_report_YYYY-MM-DD.html`

邮件和报告末尾会附带运行报告，列出各数据库的 API 调用状态和检索结果条数。

## 邮件配置

本地运行可以在终端中设置环境变量：

```bash
export SMTP_HOST="smtp.example.com"
export SMTP_PORT="587"
export SMTP_USER="your_account@example.com"
export SMTP_PASSWORD="your_password_or_app_password"
export EMAIL_TO="your_email@example.com"
```

如果邮件参数缺失，程序仍会生成报告，只是不发送邮件。

## GitHub Secrets

在 GitHub 仓库中打开：

`Settings` → `Secrets and variables` → `Actions` → `New repository secret`

建议添加：

- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USER`
- `SMTP_PASSWORD`
- `EMAIL_TO`
- `GEMINI_API_KEY`，可选，用于增强论文问题和贡献分析
- `SEMANTIC_SCHOLAR_API_KEY`，用于启用 Semantic Scholar 检索。程序会按官方要求通过 `x-api-key` 请求头发送，并默认限制为每秒最多 1 次请求。
- `ELSEVIER_API_KEY`，用于启用 Elsevier Scopus 检索。不要把 API Key 写入 `config.yaml` 或提交到仓库。
- `EASYSCHOLAR_SECRET_KEY`，用于调用 EasyScholar 开放接口查询 SCI 影响因子和 JCR 分区。不要把 SecretKey 写入 `config.yaml` 或提交到仓库。

## GitHub Actions 定时运行

工作流文件位于：

`.github/workflows/weekly-literature-alert.yml`

它会在每周一 Europe/Rome 时间上午 9 点附近运行。由于 GitHub cron 只支持 UTC，workflow 会在 07:00 和 08:00 UTC 各触发一次，并在任务开始时检查当前 Europe/Rome 时间，仅保留 09:00 的那次运行。

也可以在 GitHub 页面手动触发：

`Actions` → `Weekly Literature Alert` → `Run workflow`

## 修改关键词

编辑 `config.yaml` 中：

```yaml
keywords:
  include:
    - "composite solid electrolyte"
  exclude:
    - "aqueous electrolyte"
```

增加 `include` 可以扩大检索面；增加 `exclude` 可以减少水系电解质、超级电容器、燃料电池等噪声主题。

## 修改期刊影响因子

编辑：

```yaml
venues:
  impact_factors:
    Nature Energy: 56.7
    Energy Storage Materials: 18.9
```

当前评分只使用文章标题相关度和期刊影响因子。程序会优先使用 EasyScholar 查询到的 SCI 影响因子；如果没有配置 `EASYSCHOLAR_SECRET_KEY`、接口失败或期刊未匹配，再使用 `venues.impact_factors` 中的备用数值。

邮件中的每篇论文会显示：

```text
SCI 影响因子 / JCR 分区：18.9 / Q1（EasyScholar）
```

## 查看历史报告

历史报告保存在 `reports/`，文件名格式为：

```text
weekly_report_YYYY-MM-DD.md
weekly_report_YYYY-MM-DD.html
```

`weekly_report.md` 和 `weekly_report.html` 始终指向最近一次生成的报告。

## 去重和已推送记录

`data/seen.json` 会记录已经推送过的 DOI 或标题指纹，避免下周重复发送同一篇论文。

去重规则包括：

- DOI 归一化匹配；
- URL 匹配；
- 标题相似度匹配。

## 测试

```bash
pytest -q
```

测试覆盖：

- DOI 去重；
- 标题相似度去重；
- 文献评分函数；
- 邮件正文生成。

## 邮件发送失败排查

常见原因：

- `SMTP_HOST` 或 `SMTP_PORT` 填写错误；
- 邮箱服务商要求使用应用专用密码，而不是登录密码；
- 邮箱没有开启 SMTP；
- GitHub Secrets 名称写错；
- `EMAIL_TO` 仍是 `your_email@example.com`；
- 公司或学校邮箱阻止第三方 SMTP 登录。

排查建议：

1. 先本地运行 `python src/main.py --dry-run`，确认报告能生成。
2. 再设置 SMTP 环境变量后运行 `python src/main.py`。
3. 如果本地可发送而 GitHub Actions 不行，优先检查 GitHub Secrets 是否完整。
4. 查看 GitHub Actions 日志中的 `Failed to send report email` 信息。

## 大模型总结

没有 `GEMINI_API_KEY` 时，程序会使用规则回答“它真正想解决的问题是什么？”和“它声称的贡献是什么？”。

配置 `GEMINI_API_KEY` 后，程序会在最终推荐论文列表确定后，才调用 Gemini API 增强问题和贡献分析；候选论文池不会调用 Gemini。如果调用失败，不会中断工作流，会自动回退到基础报告。

默认模型在 `config.yaml` 中配置为 `gemini-3.1-flash-lite`。

为减少限流，`config.yaml` 中还可以调整：

```yaml
gemini:
  min_interval_seconds: 15
  retry_attempts: 2
  retry_backoff_seconds: 30
```
