# Hugging Face Papers RSS

自动获取 Hugging Face 上最新的 AI 研究论文并生成 RSS feed。

## 功能

- 每天定时自动抓取 Hugging Face 上最新的论文
- 自动翻译摘要
- 生成 RSS feed
- 自动部署到 GitHub Pages

## RSS Feed

访问地址：https://azuresilent.github.io/hf-paper-rss/feed.xml


### 环境变量（可选）

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `RSS_FEED_URL` | - | RSS feed 的完整 URL |
| `RSS_TITLE` | Hugging Face Papers RSS | Feed 标题 |
| `RSS_DESCRIPTION` | Latest AI research papers from Hugging Face | Feed 描述 |
| `TARGET_LANGUAGES` | zh-CN | 目标语言（用于翻译摘要），支持多个语言（用逗号分隔）<br>常用代码：`zh-CN`(中文)、`en`(英语)、`es`(西班牙语)、`fr`(法语)、`de`(德语)、`ja`(日语)、`ko`(韩语)、`ru`(俄语)、`it`(意大利语)、`pt`(葡萄牙语)、`ar`(阿拉伯语)、`hi`(印地语)<br>完整列表：[Google Translate 语言代码](https://cloud.google.com/translate/docs/languages) |

## GitHub Actions

项目使用 GitHub Actions 自动更新 RSS feed 并部署到 GitHub Pages。

### 配置部署 Token

为了使 GitHub Actions 能够自动部署到 GitHub Pages，你需要创建一个 Personal Access Token：

1. 前往 [GitHub Token 设置页面](https://github.com/settings/tokens?type=beta)
2. 点击 **Generate new token**，选择 **Generate new token (classic)** 或 **Fine-grained token**
3. 填写 token 名称（如 `hf-papers-rss-deploy`）
4. 配置权限：
   - **Classic Token**：勾选 `repo` 权限（包含内容读写权限）
   - **Fine-grained Token**：
     - Repository access：选择 **Only select repositories** 并勾选当前仓库
     - Repository permissions：展开并勾选 `Contents` 下的 `Read and write`
5. 点击底部的 **Generate token** 生成
6. **重要**：立即复制生成的 token，关闭页面后将无法再次查看
7. 在仓库的 **Settings → Secrets and variables → Actions** 中添加：
   - Name: `DEPLOY_TOKEN`
   - Value: 粘贴刚才复制的 token

### 定时运行

Workflow 默认每 2 小时自动运行一次（UTC 时间 01:50、03:50、05:50 ... 23:50）。

### 手动触发

你也可以手动触发 workflow：
1. 访问 [Actions 页面](https://github.com/AzureSilent/hf-paper-rss/actions)
2. 选择 "Update Hugging Face Papers RSS Feed"
3. 点击 **Run workflow** → **Run workflow** 确认

## 许可证

MIT License