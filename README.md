# Weekly Literature Alert

这是一个通用型每周最新文献播报程序。它可以根据你在 `config.yaml` 中配置的研究主题、关键词、排除词和期刊指标，自动检索最近一段时间的新论文，筛选出最值得关注的文献，生成中文 Markdown/HTML 报告，并通过邮件发送。

适用场景包括：

- 每周跟踪某个研究方向的新论文；
- 为课题组、项目或个人建立自动文献播报；
- 从多个公开学术数据库汇总候选论文；
- 按标题相关度和期刊影响因子进行初筛；
- 自动生成中文阅读提示和运行报告。

当前支持的检索和辅助信息来源包括 OpenAlex、Crossref、Semantic Scholar、Elsevier Scopus 和 EasyScholar。Gemini API 是可选项，用于对最终推荐论文生成更深入的审稿式问题分析。

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

## 功能概览

- 按关键词检索最近若干天的新论文；
- 支持 OpenAlex、Crossref、Semantic Scholar 和 Elsevier Scopus；
- 使用 EasyScholar 查询 SCI 影响因子和 JCR 分区；
- 根据 DOI、URL 和标题相似度去重；
- 使用 `data/seen.json` 避免重复推送；
- 只对最终推荐论文调用 Gemini，避免对候选池浪费额度；
- 生成 Markdown 和 HTML 两种报告；
- 通过 SMTP 发送 HTML 邮件；
- 在 GitHub Actions 中定时运行，并自动提交最新报告。

## 安装依赖

```bash
cd weekly-literature-alert
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 配置 config.yaml

核心配置都在 `config.yaml` 中。通常只需要修改以下几类字段。

### 用户信息

```yaml
profile:
  name: "Your Name"
  email_to: "your_email@example.com"
```

在 GitHub Actions 中，建议用 `EMAIL_TO` Secret 覆盖收件邮箱。

### 检索范围

```yaml
search:
  days_back: 30
  max_results_per_source: 80
  top_n: 10
  min_recommendations: 5
```

- `days_back`：检索最近多少天的论文；
- `max_results_per_source`：每个数据库最多返回多少候选论文；
- `top_n`：报告中最多推荐多少篇；
- `min_recommendations`：候选池足够时至少推荐多少篇。

### 关键词

```yaml
keywords:
  include:
    - "your main research topic"
    - "important method or material"
    - "important mechanism"
  exclude:
    - "unrelated topic"
    - "unwanted application"
```

`include` 用于检索和标题相关度评分。`exclude` 用于排除明显不相关的论文。你可以把这里替换成任何研究方向，例如医学、材料、AI、能源、环境、社会科学等。

### 期刊影响因子备用表

```yaml
venues:
  impact_factors:
    Nature: 50.5
    Science: 44.7
    Example Journal: 8.0
```

程序会优先使用 EasyScholar 查询 SCI 影响因子和 JCR 分区。如果没有配置 `EASYSCHOLAR_SECRET_KEY`、接口失败或期刊未匹配，则使用这里的备用数值。

### 评分权重

```yaml
ranking:
  weight_title_relevance: 0.70
  weight_impact_factor: 0.30
  default_impact_factor: 1.0
  max_impact_factor: 60.0
```

当前评分只使用两项：

- 论文标题与 `keywords.include` 的相关度；
- 期刊影响因子。

### Gemini 分析

```yaml
gemini:
  model: "gemini-3.1-flash-lite"
  enable_if_key_present: true
  min_interval_seconds: 15
  retry_attempts: 2
  retry_backoff_seconds: 30
```

配置 `GEMINI_API_KEY` 后，程序只会对最终推荐论文调用 Gemini。Gemini 会以严格审稿人的口吻回答：

1. 它真正想解决的问题是什么？
2. 它声称的贡献是什么？
3. 它的主要结论是什么？

如果 Gemini 调用失败，程序会自动回退到规则分析，不会中断邮件推送。

## 本地运行

只生成报告、不发送邮件：

```bash
python src/main.py --dry-run
```

生成报告并尝试发送邮件：

```bash
python src/main.py
```

输出文件保存在 `reports/`：

- `weekly_report.md`
- `weekly_report.html`
- `weekly_report_YYYY-MM-DD.md`
- `weekly_report_YYYY-MM-DD.html`

报告末尾会附带运行报告，包括各数据库检索结果、API 调用状态、EasyScholar 期刊指标查询情况，以及 Gemini API 的成功、失败、限流和规则回退情况。

## 邮件配置

本地运行可以设置以下环境变量：

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
- `GEMINI_API_KEY`，可选，用于增强最终推荐论文分析；
- `SEMANTIC_SCHOLAR_API_KEY`，可选，用于启用 Semantic Scholar 检索；
- `ELSEVIER_API_KEY`，可选，用于启用 Elsevier Scopus 检索；
- `EASYSCHOLAR_SECRET_KEY`，可选，用于查询 SCI 影响因子和 JCR 分区。

不要把任何 API Key、邮箱密码或 SecretKey 写入 `config.yaml` 或提交到仓库。

## GitHub Actions 定时运行

工作流文件位于：

```text
.github/workflows/weekly-literature-alert.yml
```

默认配置为每周一 Europe/Rome 时间上午 9 点附近运行。由于 GitHub cron 只支持 UTC，workflow 会在 07:00 和 08:00 UTC 各触发一次，并在任务开始时检查 Europe/Rome 当前时间，只保留 09:00 的那次运行。

也可以手动触发：

`Actions` → `Weekly Literature Alert` → `Run workflow`

运行完成后，workflow 会把更新后的 `reports/` 和 `data/seen.json` 自动提交回仓库。

## 修改研究方向

要把程序迁移到新的研究方向，通常只需要修改 `config.yaml`：

```yaml
keywords:
  include:
    - "target research topic"
    - "important keyword"
    - "key method"
  exclude:
    - "irrelevant field"
    - "unwanted material or application"
```

建议做法：

1. 先写 5 到 20 个核心英文关键词；
2. 加入常见同义词和缩写；
3. 把容易混入的相邻领域写入 `exclude`；
4. 本地运行 `python src/main.py --dry-run` 检查结果；
5. 根据报告中的噪声论文继续调整关键词。

## 修改期刊指标

如果 EasyScholar 未覆盖某些期刊，可以在 `config.yaml` 中维护备用影响因子：

```yaml
venues:
  impact_factors:
    Example Journal A: 12.3
    Example Journal B: 6.8
```

邮件中的每篇论文会显示类似：

```text
SCI 影响因子 / JCR 分区：12.3 / Q1（EasyScholar）
```

或在 EasyScholar 未匹配时显示配置表来源。

## 查看历史报告

历史报告保存在 `reports/`，文件名格式为：

```text
weekly_report_YYYY-MM-DD.md
weekly_report_YYYY-MM-DD.html
```

`weekly_report.md` 和 `weekly_report.html` 始终指向最近一次生成的报告。

## 去重和已推送记录

`data/seen.json` 会记录已经推送过的 DOI 或标题指纹，避免下周重复推送同一篇论文。

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
- EasyScholar 期刊指标解析；
- Gemini 分析和限流重试；
- 邮件正文和运行报告生成。

## 邮件发送失败排查

常见原因：

- `SMTP_HOST` 或 `SMTP_PORT` 填写错误；
- 邮箱服务商要求使用应用专用密码，而不是登录密码；
- 邮箱没有开启 SMTP；
- GitHub Secrets 名称写错；
- `EMAIL_TO` 仍是示例邮箱；
- 公司或学校邮箱阻止第三方 SMTP 登录。

排查建议：

1. 先本地运行 `python src/main.py --dry-run`，确认报告能生成；
2. 再设置 SMTP 环境变量后运行 `python src/main.py`；
3. 如果本地可发送而 GitHub Actions 不行，优先检查 GitHub Secrets 是否完整；
4. 查看 GitHub Actions 日志中的 `Failed to send report email` 信息。

## API 限流说明

外部 API 可能限流或短暂失败。程序会尽量跳过失败来源并继续生成报告。运行报告中会显示：

- 每个文献数据库是否成功调用；
- 每个数据库返回了多少条结果；
- EasyScholar 查询了多少个期刊、匹配多少篇论文；
- Gemini 尝试分析多少篇最终推荐论文；
- Gemini 成功、失败、429 限流和规则回退数量。
