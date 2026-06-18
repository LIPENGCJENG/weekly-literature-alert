# Weekly Literature Alert

Weekly Literature Alert 是一个通用型每周最新文献播报程序。你只需要在 GitHub 仓库中配置关键词、邮箱和 API Key，它就可以每周自动检索最新论文，筛选出值得关注的文献，并把中文报告发送到邮箱。

它适合用来：

- 每周跟踪一个研究方向的新论文；
- 给个人、课题组或项目建立自动文献播报；
- 从多个公开学术数据库汇总候选论文；
- 根据标题相关度和期刊影响因子筛选文献；
- 自动生成中文 Markdown/HTML 邮件报告。

当前支持 OpenAlex、Crossref、Semantic Scholar、Elsevier Scopus 和 EasyScholar。Gemini API 是可选项，用于对最终推荐论文生成审稿式分析。

## 它会做什么

- 按你设置的关键词检索最近若干天的新论文；
- 自动去除重复论文；
- 查询期刊 SCI 影响因子和 JCR 分区；
- 按标题相关度和期刊影响因子排序；
- 每周推荐 5 到 10 篇左右的重点论文；
- 生成中文文献播报邮件；
- 在报告末尾附上本次运行状态。

## 你需要准备什么

最少需要：

- 一个 GitHub 仓库；
- 一个可以发送邮件的 SMTP 邮箱；
- 收件邮箱地址；
- 一组与你研究方向相关的英文关键词。

可选增强：

- `SEMANTIC_SCHOLAR_API_KEY`：启用 Semantic Scholar 检索；
- `ELSEVIER_API_KEY`：启用 Elsevier Scopus 检索；
- `EASYSCHOLAR_SECRET_KEY`：查询 SCI 影响因子和 JCR 分区；
- `GEMINI_API_KEY`：为最终推荐论文生成审稿式分析。

## 第一步：配置 config.yaml

打开 `config.yaml`，重点修改以下内容。

### 收件人

```yaml
profile:
  name: "Your Name"
  email_to: "your_email@example.com"
```

### 检索范围

```yaml
search:
  days_back: 30
  max_results_per_source: 80
  top_n: 10
  min_recommendations: 5
```

常用设置：

- `days_back`：检索最近多少天；
- `top_n`：最多推荐多少篇；
- `min_recommendations`：至少推荐多少篇。

### 关键词

```yaml
keywords:
  include:
    - "your main research topic"
    - "important method"
    - "important material"
  exclude:
    - "unrelated topic"
    - "unwanted application"
```

建议先写 5 到 20 个英文关键词。`include` 写你想追踪的主题，`exclude` 写你不想收到的相邻领域或噪声主题。

### 评分方式

```yaml
ranking:
  weight_title_relevance: 0.70
  weight_impact_factor: 0.30
```

当前评分主要由两部分组成：

- 标题与关键词的相关度；
- 期刊影响因子。

## 第二步：配置 GitHub Secrets

在 GitHub 仓库页面进入：

`Settings` → `Secrets and variables` → `Actions` → `New repository secret`

建议添加：

- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USER`
- `SMTP_PASSWORD`
- `EMAIL_TO`
- `SEMANTIC_SCHOLAR_API_KEY`
- `ELSEVIER_API_KEY`
- `EASYSCHOLAR_SECRET_KEY`
- `GEMINI_API_KEY`

其中 SMTP 和 `EMAIL_TO` 用于发送邮件。其余 API Key 可以先不填，程序会跳过未配置的数据源或功能。

不要把邮箱密码或 API Key 写进 `config.yaml`。

## 第三步：启动 GitHub Actions

项目已经包含自动运行文件：

```text
.github/workflows/weekly-literature-alert.yml
```

默认会在每周一 Europe/Rome 时间上午 9 点附近自动运行。

你也可以手动触发一次运行：

`Actions` → `Weekly Literature Alert` → `Run workflow`

运行完成后，你会收到一封 HTML 邮件，同时仓库中的 `reports/` 文件夹会保存最新报告。

## 邮件里会包含什么

每篇推荐论文会包含：

- 论文标题；
- 作者；
- 期刊或平台；
- SCI 影响因子 / JCR 分区；
- 发表日期；
- DOI；
- 相关性评分；
- 它真正想解决的问题是什么；
- 它声称的贡献是什么；
- 它的主要结论是什么。

报告最后还会显示运行状态，例如各数据库返回了多少结果、EasyScholar 是否查询成功、Gemini 是否成功调用等。

## 高级说明

更完整的开发和维护说明请看：

[developerdoc.md](developerdoc.md)

其中包含更完整的维护、调试和二次开发说明。
