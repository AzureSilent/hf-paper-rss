#!/usr/bin/env python3
"""
Hugging Face Daily Papers Page Generator
Fetches papers from a specific date and generates an HTML page
Reuses functions and cache from generate_rss.py
"""

import argparse
import glob
import os
import time
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import sys

# Import from generate_rss.py
from generate_rss import (
    PaperExtractor,
    fetch_with_retry,
    process_paper,
    load_processed_papers,
    save_processed_papers,
    MAX_WORKERS,
    TARGET_LANGUAGES,
    logger
)

# ============= HTML Generation =============
def get_css() -> str:
    """Get CSS styles"""
    return '''
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
            min-height: 100vh;
            color: #e0e0e0;
            padding: 20px;
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
        }
        
        header {
            text-align: center;
            margin-bottom: 40px;
            padding: 30px;
            background: rgba(255, 255, 255, 0.05);
            border-radius: 16px;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.1);
        }
        
        h1 {
            font-size: 2.5em;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            margin-bottom: 10px;
        }
        
        .date {
            font-size: 1.2em;
            color: #a0a0a0;
        }
        
        .stats {
            margin-top: 15px;
            display: flex;
            justify-content: center;
            gap: 30px;
        }
        
        .stat-item {
            text-align: center;
        }
        
        .stat-number {
            font-size: 2em;
            font-weight: bold;
            color: #667eea;
        }
        
        .stat-label {
            font-size: 0.9em;
            color: #888;
        }
        
        .paper-card {
            background: rgba(255, 255, 255, 0.05);
            border-radius: 16px;
            padding: 25px;
            margin-bottom: 20px;
            border: 1px solid rgba(255, 255, 255, 0.1);
            transition: all 0.3s ease;
            backdrop-filter: blur(5px);
        }
        
        .paper-card:hover {
            transform: translateY(-2px);
            border-color: rgba(102, 126, 234, 0.5);
            box-shadow: 0 10px 40px rgba(102, 126, 234, 0.2);
        }
        
        .paper-title {
            font-size: 1.3em;
            font-weight: 600;
            margin-bottom: 12px;
            line-height: 1.4;
        }
        
        .paper-title a {
            color: #e0e0e0;
            text-decoration: none;
            transition: color 0.2s;
        }
        
        .paper-title a:hover {
            color: #667eea;
        }
        
        .paper-meta {
            display: flex;
            flex-wrap: wrap;
            gap: 15px;
            margin-bottom: 15px;
            font-size: 0.9em;
            color: #a0a0a0;
        }
        
        .meta-item {
            display: flex;
            align-items: center;
            gap: 5px;
        }
        
        .meta-label {
            color: #888;
        }
        
        .links {
            display: flex;
            gap: 15px;
            margin-bottom: 15px;
        }
        
        .link-btn {
            display: inline-flex;
            align-items: center;
            gap: 5px;
            padding: 8px 16px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            text-decoration: none;
            border-radius: 8px;
            font-size: 0.9em;
            font-weight: 500;
            transition: all 0.2s;
        }
        
        .link-btn:hover {
            transform: scale(1.05);
            box-shadow: 0 5px 20px rgba(102, 126, 234, 0.4);
        }
        
        .link-btn.secondary {
            background: rgba(255, 255, 255, 0.1);
            border: 1px solid rgba(255, 255, 255, 0.2);
        }
        
        .link-btn.secondary:hover {
            background: rgba(255, 255, 255, 0.15);
        }
        
        .abstract-section {
            margin-top: 15px;
        }
        
        .abstract-header {
            display: flex;
            align-items: center;
            gap: 10px;
            cursor: pointer;
            padding: 10px 15px;
            background: rgba(255, 255, 255, 0.05);
            border-radius: 8px;
            transition: background 0.2s;
        }
        
        .abstract-header:hover {
            background: rgba(255, 255, 255, 0.1);
        }
        
        .abstract-toggle {
            width: 20px;
            height: 20px;
            border-radius: 50%;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 12px;
            color: white;
            transition: transform 0.3s;
        }
        
        .abstract-toggle.expanded {
            transform: rotate(180deg);
        }
        
        .abstract-label {
            font-weight: 500;
            color: #667eea;
        }
        
        .abstract-content {
            max-height: 0;
            overflow: hidden;
            transition: max-height 0.3s ease-out;
            padding: 0 15px;
        }
        
        .abstract-content.expanded {
            max-height: 10000px;
            padding: 15px;
        }
        
        .abstract-text {
            line-height: 1.7;
            color: #c0c0c0;
        }
        
        .summary-box {
            background: rgba(102, 126, 234, 0.1);
            border-left: 3px solid #667eea;
            padding: 12px 15px;
            margin-bottom: 15px;
            border-radius: 0 8px 8px 0;
        }
        
        .summary-label {
            font-size: 0.8em;
            color: #667eea;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 5px;
        }
        
        .summary-text {
            color: #b0b0b0;
            line-height: 1.5;
        }
        
        .translation-box {
            background: rgba(118, 75, 162, 0.1);
            border-left: 3px solid #764ba2;
            padding: 12px 15px;
            margin-bottom: 15px;
            border-radius: 0 8px 8px 0;
        }
        
        .translation-label {
            font-size: 0.8em;
            color: #764ba2;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 5px;
        }
        
        .translation-text {
            color: #b0b0b0;
            line-height: 1.5;
        }
        
        footer {
            text-align: center;
            margin-top: 40px;
            padding: 20px;
            color: #666;
            font-size: 0.9em;
        }
        
        footer a {
            color: #667eea;
            text-decoration: none;
        }
        
        .nav-buttons {
            display: flex;
            justify-content: space-between;
            margin-top: 30px;
            padding: 0 10px;
        }
        
        .nav-btn {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 12px 24px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            text-decoration: none;
            border-radius: 8px;
            font-size: 1em;
            font-weight: 500;
            transition: all 0.2s;
        }
        
        .nav-btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 20px rgba(102, 126, 234, 0.4);
        }
        
        .nav-btn.disabled {
            background: rgba(255, 255, 255, 0.1);
            color: #666;
            pointer-events: none;
        }
        
        @media (max-width: 768px) {
            h1 {
                font-size: 1.8em;
            }
            
            .stats {
                flex-direction: column;
                gap: 15px;
            }
            
            .paper-title {
                font-size: 1.1em;
            }
            
            .links {
                flex-wrap: wrap;
            }
            
            .nav-buttons {
                flex-direction: column;
                gap: 15px;
            }
            
            .nav-btn {
                justify-content: center;
            }
        }
    '''


def generate_html(papers: list, date_str: str, prev_date: str, next_date: str, 
                  lang: str = None, lang_path_prefix: str = "") -> str:
    """Generate HTML page with collapsible abstracts
    
    Args:
        papers: List of paper dictionaries
        date_str: Current date string (yyyy-mm-dd)
        prev_date: Previous date string for navigation
        next_date: Next date string for navigation
        lang: Target language code (e.g., 'zh-CN'), None for original
        lang_path_prefix: Path prefix for language subdirectory (e.g., '../')
    """
    lang_attr = lang if lang else "en"
    title_suffix = f" ({lang})" if lang else ""
    
    # Build navigation paths
    def get_nav_path(target_date: str) -> str:
        # Both original and translated versions use relative path in the same directory
        return f"{target_date}.html"
    
    html = f'''<!DOCTYPE html>
<html lang="{lang_attr}">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Hugging Face Papers - {date_str}{title_suffix}</title>
    <style>{get_css()}</style>
</head>
<body>
    <div class="container">
        <header>
            <h1>Hugging Face Papers</h1>
            <div class="date">{date_str}</div>
            <div class="stats">
                <div class="stat-item">
                    <div class="stat-number">{len(papers)}</div>
                    <div class="stat-label">Papers</div>
                </div>
            </div>
        </header>
        
        <main>
'''
    
    for paper in papers:
        institution = paper.get('institution', 'N/A')
        authors = paper.get('authors', [])
        authors_str = ', '.join(authors) if authors else 'N/A'
        arxiv_abs = paper.get('arxiv_abs')
        arxiv_pdf = paper.get('arxiv_pdf')
        abstract_short = paper.get('abstract_short', '[Not available]')
        abstract_full = paper.get('abstract', '[Not available]')
        
        # Get translated content if language specified
        translated_summary = ""
        translated_abstract = ""
        if lang:
            translated_summary = paper.get(f'description_{lang}', '')
            translated_abstract = paper.get(f'abstractFull_{lang}', '')
        
        html += f'''
            <div class="paper-card">
                <h2 class="paper-title">
                    <a href="{paper['url']}" target="_blank">{paper['title']}</a>
                </h2>
                
                <div class="paper-meta">
                    <div class="meta-item">
                        <span class="meta-label">Institution:</span>
                        <span>{institution}</span>
                    </div>
                    <div class="meta-item">
                        <span class="meta-label">Authors:</span>
                        <span>{authors_str}</span>
                    </div>
                </div>
                
                <div class="links">
                    <a href="{paper['url']}" target="_blank" class="link-btn">HF Page</a>
'''
        
        if arxiv_abs:
            html += f'                    <a href="{arxiv_abs}" target="_blank" class="link-btn secondary">arXiv</a>\n'
        if arxiv_pdf:
            html += f'                    <a href="{arxiv_pdf}" target="_blank" class="link-btn secondary">PDF</a>\n'
        
        html += f'''                </div>
                
                <div class="summary-box">
                    <div class="summary-label">AI Summary</div>
                    <div class="summary-text">{abstract_short}</div>
                </div>
'''
        
        # Add translated summary if available
        if translated_summary and translated_summary != abstract_short:
            html += f'''
                <div class="translation-box">
                    <div class="translation-label">Translation ({lang})</div>
                    <div class="translation-text">{translated_summary}</div>
                </div>
'''
        
        html += f'''
                <div class="abstract-section">
                    <div class="abstract-header" onclick="toggleAbstract(this)">
                        <span class="abstract-toggle">▼</span>
                        <span class="abstract-label">Abstract (click to expand)</span>
                    </div>
                    <div class="abstract-content">
                        <p class="abstract-text">{abstract_full}</p>
'''
        
        # Add translated abstract if available
        if translated_abstract and translated_abstract != abstract_full:
            html += f'''
                        <br>
                        <p class="abstract-text"><strong>Translation ({lang}):</strong></p>
                        <p class="abstract-text">{translated_abstract}</p>
'''
        
        html += '''                    </div>
                </div>
            </div>
'''
    
    # Navigation buttons
    prev_path = get_nav_path(prev_date)
    next_path = get_nav_path(next_date)
    
    html += f'''
        </main>
        
        <div class="nav-buttons">
            <a href="{prev_path}" class="nav-btn">← {prev_date}</a>
            <a href="{next_path}" class="nav-btn">{next_date} →</a>
        </div>
        
        <footer>
            Generated by <a href="https://github.com" target="_blank">HF Papers Daily</a>
        </footer>
    </div>
    
    <script>
        function toggleAbstract(header) {{
            const toggle = header.querySelector('.abstract-toggle');
            const content = header.nextElementSibling;
            toggle.classList.toggle('expanded');
            content.classList.toggle('expanded');
        }}
    </script>
</html>
'''
    
    return html


def save_html(content: str, filepath: str):
    """Save HTML content to file, creating directories if needed"""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    logger.info(f"Saved: {filepath}")


# ============= Cleanup Old Files =============
def cleanup_old_files(output_dir: str, keep_days: int = 60):
    """Remove HTML files older than keep_days
    
    Args:
        output_dir: Base output directory (e.g., 'docs/date')
        keep_days: Number of days to keep (default: 60)
    """
    import glob
    
    cutoff_date = datetime.now() - timedelta(days=keep_days)
    cutoff_str = cutoff_date.strftime('%Y-%m-%d')
    
    deleted_count = 0
    
    # Clean up files in the base directory
    pattern = os.path.join(output_dir, '*.html')
    for filepath in glob.glob(pattern):
        filename = os.path.basename(filepath)
        # Extract date from filename (yyyy-mm-dd.html)
        if len(filename) >= 10 and filename[:4].isdigit():
            file_date = filename[:10]
            if file_date < cutoff_str:
                os.remove(filepath)
                logger.info(f"Deleted old file: {filepath}")
                deleted_count += 1
    
    # Clean up files in language subdirectories
    for lang in TARGET_LANGUAGES:
        if not lang.strip():
            continue
        lang_dir = os.path.join(output_dir, lang.strip())
        if os.path.isdir(lang_dir):
            pattern = os.path.join(lang_dir, '*.html')
            for filepath in glob.glob(pattern):
                filename = os.path.basename(filepath)
                if len(filename) >= 10 and filename[:4].isdigit():
                    file_date = filename[:10]
                    if file_date < cutoff_str:
                        os.remove(filepath)
                        logger.info(f"Deleted old file: {filepath}")
                        deleted_count += 1
    
    if deleted_count > 0:
        logger.info(f"Cleanup complete: removed {deleted_count} files older than {keep_days} days")
    else:
        logger.info(f"No files to clean up (keeping last {keep_days} days)")


# ============= Main Function =============
def main():
    """Main function"""
    parser = argparse.ArgumentParser(description='Fetch Hugging Face papers for a specific date')
    parser.add_argument('--date', '-d', type=str, help='Date in yyyy-mm-dd format (default: yesterday)')
    parser.add_argument('--output-dir', '-o', type=str, default='docs/date', help='Output directory')
    parser.add_argument('--keep-days', '-k', type=int, default=60, help='Keep files from last N days (default: 60)')
    args = parser.parse_args()
    
    # Determine the date
    if args.date:
        try:
            date_obj = datetime.strptime(args.date, '%Y-%m-%d')
        except ValueError:
            logger.error(f"Invalid date format: {args.date}. Use yyyy-mm-dd format.")
            sys.exit(1)
    else:
        date_obj = datetime.now() - timedelta(days=1)
    
    date_str = date_obj.strftime('%Y-%m-%d')
    
    # Calculate prev/next dates for navigation
    prev_date = (date_obj - timedelta(days=1)).strftime('%Y-%m-%d')
    next_date = (date_obj + timedelta(days=1)).strftime('%Y-%m-%d')
    
    output_dir = args.output_dir
    
    # Check if all target HTML files already exist
    # all_files_exist = True
    # files_to_check = [os.path.join(output_dir, f"{date_str}.html")]
    # for lang in TARGET_LANGUAGES:
    #     if lang.strip():
    #         files_to_check.append(os.path.join(output_dir, lang.strip(), f"{date_str}.html"))
    
    # for filepath in files_to_check:
    #     if not os.path.exists(filepath):
    #         all_files_exist = False
    #         break
    
    # if all_files_exist:
    #     logger.info("=" * 60)
    #     logger.info(f"All files already exist for: {date_str}")
    #     for filepath in files_to_check:
    #         logger.info(f"  ✓ {filepath}")
    #     logger.info("Skipping...")
    #     cleanup_old_files(output_dir, keep_days=args.keep_days)
    #     logger.info("=" * 60)
    #     return
    
    url = f"https://huggingface.co/papers/date/{date_str}"
    
    logger.info("=" * 60)
    logger.info(f"Fetching papers for: {date_str}")
    logger.info(f"URL: {url}")
    logger.info(f"Target languages: {TARGET_LANGUAGES}")
    logger.info("=" * 60)
    
    start = time.time()
    
    try:
        # Load cache from generate_rss.py
        processed_dict, paper_cache = load_processed_papers()
        
        # Fetch paper list
        logger.info("Fetching paper list...")
        html = fetch_with_retry(url)
        
        # Parse paper list
        extractor = PaperExtractor()
        extractor.feed(html)
        papers = extractor.papers
        logger.info(f"Found {len(papers)} papers")
        
        if not papers:
            logger.warning("No papers found for this date!")
            return
        
        # Count cache hits
        cached_count = sum(1 for p in papers if p['url'] in processed_dict)
        logger.info(f"Cache hits: {cached_count}/{len(papers)}")
        
        # Process paper details (with cache support)
        logger.info(f"Processing {len(papers)} papers...")
        results = [None] * len(papers)
        
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_to_index = {
                executor.submit(process_paper, paper, processed_dict, paper_cache): i 
                for i, paper in enumerate(papers)
            }
            
            for future in as_completed(future_to_index):
                index = future_to_index[future]
                try:
                    result = future.result()
                    results[index] = result
                    logger.info(f"[{index + 1}/{len(papers)}] Done: {result['title'][:40]}...")
                except Exception as e:
                    paper = papers[index]
                    logger.error(f"[{index + 1}/{len(papers)}] Failed: {paper['title'][:40]}...: {e}")
                    results[index] = paper
        
        # Generate and save HTML files
        logger.info("Generating HTML files...")
        
        # Save original version (no language)
        html_content = generate_html(results, date_str, prev_date, next_date)
        save_html(html_content, os.path.join(output_dir, f"{date_str}.html"))
        
        # Save translated versions for each target language
        for lang in TARGET_LANGUAGES:
            if not lang.strip():
                continue
            lang = lang.strip()
            html_content = generate_html(results, date_str, prev_date, next_date, 
                                        lang=lang, lang_path_prefix="../")
            save_html(html_content, os.path.join(output_dir, lang, f"{date_str}.html"))
        
        # Update cache
        save_processed_papers(results, processed_dict, paper_cache)
        
        # Cleanup old files
        cleanup_old_files(output_dir, keep_days=args.keep_days)
        
        elapsed = time.time() - start
        logger.info("=" * 60)
        logger.info("Summary:")
        logger.info(f"   Papers: {len(papers)}")
        logger.info(f"   Cached: {cached_count}")
        logger.info(f"   Output dir: {output_dir}")
        logger.info(f"   Languages: original + {len([l for l in TARGET_LANGUAGES if l.strip()])} translations")
        logger.info(f"   Time: {elapsed:.2f}s")
        logger.info("=" * 60)
        logger.info("Done!")
        
    except Exception as e:
        logger.error(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
