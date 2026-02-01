# Hugging Face Papers RSS

Automatically fetches the latest AI research papers from Hugging Face and generates an RSS feed.

**其他语言 / Other Languages**: [简体中文](README.zh-CN.md)

## Features

- Automatically scrapes the latest papers from Hugging Face on a scheduled basis
- Automatically translates abstracts
- Generates RSS feed
- Auto-deploys to GitHub Pages

## RSS Feed

Access URL: https://azuresilent.github.io/hf-paper-rss/feed.xml

## Local Development

### Requirements

- Python 3.7+

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Generate RSS Feed

```bash
python generate_rss.py
```

The generated RSS feed will be saved in `docs/feed.xml`.

### Environment Variables (Optional)

| Variable | Default | Description |
|----------|---------|-------------|
| `RSS_FEED_URL` | - | Full URL of the RSS feed |
| `RSS_TITLE` | Hugging Face Papers RSS | Feed title |
| `RSS_DESCRIPTION` | Latest AI research papers from Hugging Face | Feed description |
| `TARGET_LANGUAGES` | zh-CN | Target languages for abstract translation (comma-separated for multiple)<br>Common codes: `zh-CN`(Chinese), `en`(English), `es`(Spanish), `fr`(French), `de`(German), `ja`(Japanese), `ko`(Korean), `ru`(Russian), `it`(Italian), `pt`(Portuguese), `ar`(Arabic), `hi`(Hindi)<br>Full list: [Google Translate language codes](https://cloud.google.com/translate/docs/languages) |

## GitHub Actions

The project uses GitHub Actions to automatically update the RSS feed and deploy to GitHub Pages.

### Setting Up Deployment Token

To enable GitHub Actions to deploy to GitHub Pages, you need to create a Personal Access Token:

1. Go to [GitHub Token Settings](https://github.com/settings/tokens?type=beta)
2. Click **Generate new token**, choose **Generate new token (classic)** or **Fine-grained token**
3. Enter a token name (e.g., `hf-papers-rss-deploy`)
4. Configure permissions:
   - **Classic Token**: Check the `repo` permission (includes content read/write access)
   - **Fine-grained Token**:
     - Repository access: Select **Only select repositories** and check the current repository
     - Repository permissions: Expand and check `Read and write` under `Contents`
5. Click **Generate token** at the bottom
6. **Important**: Copy the generated token immediately, as you won't be able to view it again after closing the page
7. Add it to your repository's **Settings → Secrets and variables → Actions**:
   - Name: `DEPLOY_TOKEN`
   - Value: Paste the token you just copied

### Scheduled Runs

The workflow runs automatically every 2 hours by default (at 01:50, 03:50, 05:50 ... 23:50 UTC).

### Manual Trigger

You can also manually trigger the workflow:
1. Visit the [Actions page](https://github.com/AzureSilent/hf-paper-rss/actions)
2. Select "Update Hugging Face Papers RSS Feed"
3. Click **Run workflow** → **Run workflow** to confirm

## License

MIT License