#!/usr/bin/env python3
"""
Hugging Face Papers RSS Feed Generator
Automatically scrapes Hugging Face Papers pages and generates an RSS 2.0 feed
"""

import os
import requests
from html.parser import HTMLParser
import re
import time
from datetime import datetime, timezone, timedelta
import xml.etree.ElementTree as ET
import xml.dom.minidom as minidom
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from deep_translator import GoogleTranslator
import json

# ============= Configuration =============
# All configurations are read from environment variables, with defaults if not set
BASE_URL = os.environ.get("BASE_URL", "https://huggingface.co/papers")
REQUEST_TIMEOUT = int(os.environ.get("REQUEST_TIMEOUT", "30"))
MAX_PAPERS = int(os.environ.get("MAX_PAPERS", "100"))
MAX_RETRIES = int(os.environ.get("MAX_RETRIES", "3"))
MAX_WORKERS = int(os.environ.get("MAX_WORKERS", "5"))

# Incremental update configuration
PROCESSED_PAPERS_FILE = os.environ.get("PROCESSED_PAPERS_FILE", ".processed_papers.json")
MAX_PROCESSED_RECORDS = int(os.environ.get("MAX_PROCESSED_RECORDS", "500"))  # Keep at most 500 records
CACHE_VERSION = int(os.environ.get("CACHE_VERSION", "1"))  # Cache format version (v3 stores full paper info)

# Translation configuration (target language list, supports multiple languages)
# Format: zh-CN,es,fr (comma-separated)
TARGET_LANGUAGES = os.environ.get("TARGET_LANGUAGES", "zh-CN").split(",")


# ============= Logging Configuration =============
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('hf_papers_rss.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# ============= Incremental Update =============
def load_processed_papers():
    """Load processed papers list and complete cache information"""
    if not os.path.exists(PROCESSED_PAPERS_FILE):
        return {}, {}
    
    try:
        with open(PROCESSED_PAPERS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
            # Check cache version
            cache_version = data.get('version', 1)
            if cache_version != CACHE_VERSION:
                logger.warning(f"Cache version mismatch: expected {CACHE_VERSION}, got {cache_version}. Ignoring old cache.")
                return {}, {}
            
            # Return two dictionaries:
            # 1. {url: timestamp} - used to determine if already processed
            # 2. {url: paper_data} - used to restore complete paper information
            processed_timestamps = data.get('papers', {})
            paper_cache = data.get('paper_cache', {})
            logger.info(f"📦 Loaded {len(processed_timestamps)} processed papers from cache (v{cache_version})")
            logger.info(f"📋 Full cache contains {len(paper_cache)} papers")
            return processed_timestamps, paper_cache
    except Exception as e:
        logger.warning(f"Failed to load processed papers: {e}")
        return {}, {}

def save_processed_papers(papers, processed_dict, paper_cache):
    """Save processed papers list and complete cache information"""
    current_time = datetime.now(timezone.utc).isoformat()
    
    # Only add timestamp and full info for new papers, keep original data for existing ones
    new_papers_count = 0
    for paper in papers:
        if paper['url'] not in processed_dict:
            processed_dict[paper['url']] = current_time
            # Save complete paper info to paper_cache
            paper_cache[paper['url']] = {
                'title': paper['title'],
                'url': paper['url'],
                'institution': paper.get('institution', 'N/A'),
                'abstract': paper.get('abstract', ''),
                'abstract_short': paper.get('abstract_short', ''),
                'arxiv_abs': paper.get('arxiv_abs'),
                'arxiv_pdf': paper.get('arxiv_pdf'),
                'authors': paper.get('authors', []),
                'pub_date': paper.get('pub_date'),  # Save the first discovered time
                # Save translated content
                'translations': {
                    'descriptions': {lang: paper.get(f'description_{lang}', '') for lang in TARGET_LANGUAGES},
                    'abstract_fulls': {lang: paper.get(f'abstractFull_{lang}', '') for lang in TARGET_LANGUAGES}
                }
            }
            new_papers_count += 1
    
    logger.info(f"📝 Added {new_papers_count} new papers to cache")
    
    # Clean up old records: keep the most recent MAX_PROCESSED_RECORDS entries
    if len(processed_dict) > MAX_PROCESSED_RECORDS:
        # Sort by timestamp, keep the newest
        sorted_items = sorted(processed_dict.items(), key=lambda x: x[1], reverse=True)
        old_size = len(processed_dict)
        kept_urls = set(item[0] for item in sorted_items[:MAX_PROCESSED_RECORDS])
        processed_dict = {url: processed_dict[url] for url in kept_urls}
        paper_cache = {url: paper_cache[url] for url in kept_urls if url in paper_cache}
        logger.info(f"🧹 Cleaned cache: removed {old_size - len(processed_dict)} old records, kept {len(processed_dict)} most recent papers")
    
    try:
        with open(PROCESSED_PAPERS_FILE, 'w', encoding='utf-8') as f:
            json.dump({
                'version': CACHE_VERSION,
                'papers': processed_dict,
                'paper_cache': paper_cache,
                'last_updated': current_time
            }, f, indent=2)
        logger.info(f"💾 Saved {len(processed_dict)} processed papers and {len(paper_cache)} full cache entries (v{CACHE_VERSION})")
    except Exception as e:
        logger.warning(f"Failed to save processed papers: {e}")

# ============= HTML Parsing =============
class PaperExtractor(HTMLParser):
    """Extract paper information from Hugging Face Papers pages"""

    def __init__(self):
        super().__init__()
        self.papers = []
        self.current_paper = None
        self.in_article = False
        self.in_h3 = False
        self.in_a = False
        self.capture_text = False
        self.current_text = ""
        self.in_institution_span = False
        self.institution_text = ""

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        class_name = attrs_dict.get("class", "")
        
        if tag == "article":
            self.in_article = True
            self.current_paper = {}

        if self.in_article and tag == "h3":
            self.in_h3 = True

        if self.in_h3 and tag == "a":
            self.in_a = True
            href = attrs_dict.get("href", "")
            if href:
                self.current_paper["url"] = "https://huggingface.co" + href
            self.capture_text = True
            self.current_text = ""

        if self.in_article and not self.in_h3 and not self.in_a and tag == "span":
            if "truncate" in class_name and "font-medium" in class_name:
                self.in_institution_span = True
                self.institution_text = ""

    def handle_endtag(self, tag):
        if tag == "a" and self.in_a:
            self.in_a = False
            if self.current_text:
                self.current_paper["title"] = self.current_text.strip()
            self.capture_text = False

        if tag == "h3" and self.in_h3:
            self.in_h3 = False

        if tag == "span" and self.in_institution_span:
            self.in_institution_span = False

        if tag == "article" and self.in_article:
            if self.current_paper and self.current_paper.get("title") and self.current_paper.get("url"):
                # Clean up institution info
                institution = re.sub(r'\s+', ' ', self.institution_text).strip()
                if not institution or institution in ["·", "."]:
                    institution = "N/A"
                self.current_paper["institution"] = institution
                self.papers.append(self.current_paper.copy())
            self.in_article = False
            self.current_paper = None
            self.institution_text = ""

    def handle_data(self, data):
        if self.capture_text:
            self.current_text += data

        if self.in_institution_span:
            self.institution_text += data

# ============= Data Extraction =============
def fetch_with_retry(url: str) -> str:
    """Fetch page content with retry"""
    for attempt in range(MAX_RETRIES):
        try:
            response = requests.get(url, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            logger.info(f"Fetched {url} ({len(response.text)} bytes)")
            return response.text
        except Exception as e:
            logger.warning(f"Attempt {attempt + 1}/{MAX_RETRIES} failed: {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 * (attempt + 1))
    raise Exception(f"Failed to fetch {url} after {MAX_RETRIES} attempts")

def extract_abstracts(html: str) -> dict:
    """Extract abstracts, authors, and arXiv links"""
    result = {
        'abstract_short': None,
        'abstract_full': None,
        'arxiv_abs': None,
        'arxiv_pdf': None,
        'authors': []
    }

    # Short abstract
    match_short = re.search(r'<div[^>]*class="[^"]*pb-8 pr-4 md:pr-16[^"]*"[^>]*>(.*?)</div>', html, re.DOTALL)
    if match_short:
        result['abstract_short'] = re.sub(r'<[^>]+>', '', match_short.group(1)).strip()
    else:
        result['abstract_short'] = "[Not available]"

    # Full abstract (second p tag)
    abstract_match = re.search(r'<h2[^>]*>Abstract</h2>', html)
    if abstract_match:
        start = abstract_match.end()
        next_h2 = re.search(r'<h2', html[start:])
        if next_h2:
            p_tags = re.findall(r'<p[^>]*>(.*?)</p>', html[start:start + next_h2.start()], re.DOTALL)
            if len(p_tags) >= 2:
                result['abstract_full'] = re.sub(r'<[^>]+>', '', p_tags[1]).strip()
                result['abstract_full'] = re.sub(r'^AI-generated summary\s*', '', result['abstract_full'])
            else:
                result['abstract_full'] = result['abstract_short']
        else:
            result['abstract_full'] = result['abstract_short']
    else:
        result['abstract_full'] = result['abstract_short']

    # Extract author info (from JSON data-props paper.authors)
    authors = []
    # Decode HTML entities first (&quot; -> ")
    html_decoded = html.replace('&quot;', '"')
    
    # Find paper.authors JSON array
    paper_authors_match = re.search(r'"authors":\s*\[(.*?)\]', html_decoded, re.DOTALL)
    if paper_authors_match:
        authors_json = paper_authors_match.group(1)
        # Extract all "name" field values
        author_names = re.findall(r'"name":\s*"([^"]+)"', authors_json)
        for name in author_names[:5]:  # Max 5 authors
            if name:
                authors.append(name)
    
    result['authors'] = authors

    # arXiv links
    paper_id = re.search(r'papers/(\d+\.\d+)', html)
    if paper_id:
        pid = paper_id.group(1)
        result['arxiv_abs'] = f"https://arxiv.org/abs/{pid}"
        result['arxiv_pdf'] = f"https://arxiv.org/pdf/{pid}.pdf"

    return result

def translate_with_retry(text: str, lang: str, max_retries: int = 3) -> str:
    """Translate text with retry"""
    for attempt in range(max_retries):
        try:
            translator = GoogleTranslator(source='auto', target=lang)
            return translator.translate(text)
        except Exception as e:
            logger.warning(f"Translation attempt {attempt + 1}/{max_retries} failed for {lang}: {e}")
            if attempt < max_retries - 1:
                time.sleep(10)
    return text  # Return original text if all retries fail

def process_paper(paper: dict, processed_dict: dict = None, paper_cache: dict = None) -> dict:
    """Process detailed information for a single paper"""
    # If already processed, return complete data from cache without fetching the page
    if processed_dict and paper['url'] in processed_dict and paper_cache:
        cached_paper = paper_cache.get(paper['url'])
        if cached_paper:
            logger.info(f"⏭️  Restoring from cache: {paper['title'][:50]}")
            # Build result dictionary
            result = {
                'title': cached_paper['title'],
                'url': cached_paper['url'],
                'institution': cached_paper.get('institution', 'N/A'),
                'abstract': cached_paper.get('abstract', ''),
                'abstract_short': cached_paper.get('abstract_short', ''),
                'arxiv_abs': cached_paper.get('arxiv_abs'),
                'arxiv_pdf': cached_paper.get('arxiv_pdf'),
                'authors': cached_paper.get('authors', []),
                'pub_date': paper.get('pub_date', cached_paper.get('pub_date', datetime.now(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S GMT')))
            }
            # Restore translated content
            translations = cached_paper.get('translations', {})
            for lang in TARGET_LANGUAGES:
                desc_key = f'description_{lang}'
                abs_key = f'abstractFull_{lang}'
                result[desc_key] = translations.get('descriptions', {}).get(lang, '')
                result[abs_key] = translations.get('abstract_fulls', {}).get(lang, '')
            return result
    
    # New paper, process fully
    try:
        html = fetch_with_retry(paper['url'])
        details = extract_abstracts(html)
        
        paper.update({
            'abstract': details['abstract_full'],
            'abstract_short': details['abstract_short'],
            'arxiv_abs': details['arxiv_abs'],
            'arxiv_pdf': details['arxiv_pdf'],
            'authors': details['authors']
        })
        
        # Translate description and abstractFull
        logger.info(f"🌐 Translating: {paper['title'][:50]}")
        
        # Translate short abstract
        if paper['abstract_short'] and paper['abstract_short'] != "[Not available]":
            for lang in TARGET_LANGUAGES:
                field_name = f'description_{lang}'
                paper[field_name] = translate_with_retry(paper['abstract_short'], lang)
        
        # Translate full abstract
        if paper['abstract'] and paper['abstract'] != "[Not available]":
            for lang in TARGET_LANGUAGES:
                field_name = f'abstractFull_{lang}'
                paper[field_name] = translate_with_retry(paper['abstract'], lang)
        
        logger.info(f"Processed: {paper['title'][:50]}")
        return paper
    except Exception as e:
        logger.error(f"Failed: {paper['title'][:50]}: {e}")
        paper['abstract'] = f"[Error: {str(e)}]"
        paper['abstract_short'] = paper['abstract']
        return paper

# ============= Main Scraping Function =============
def scrape_papers(processed_dict=None, paper_cache=None):
    """Scrape paper list (using concurrent execution)"""
    logger.info("="*60)
    logger.info("🚀 Scraping Hugging Face Papers...")
    logger.info(f"📊 {BASE_URL}")
    logger.info(f"⏰ Timeout: {REQUEST_TIMEOUT}s")
    logger.info(f"📝 Max papers: {MAX_PAPERS}")
    logger.info(f"⚡ Workers: {MAX_WORKERS}")
    if processed_dict:
        logger.info(f"📦 Cache: {len(processed_dict)} papers in cache")
    if paper_cache:
        logger.info(f"📋 Full cache: {len(paper_cache)} papers")
    logger.info("="*60)

    # Get paper list
    logger.info("📄 Fetching papers list...")
    html = fetch_with_retry(BASE_URL)

    # Parse paper list
    parser = PaperExtractor()
    parser.feed(html)
    papers = parser.papers[:MAX_PAPERS]
    logger.info(f"✅ Found {len(papers)} papers")

    if not papers:
        return []

    # Count new papers
    new_papers = [p for p in papers if processed_dict is None or p['url'] not in processed_dict]
    if processed_dict:
        logger.info(f"🆕 New papers: {len(new_papers)}, Cached: {len(papers) - len(new_papers)}")

    # Pre-generate pub_date for new papers to avoid concurrency issues
    base_time = datetime.now(timezone.utc)
    for i, paper in enumerate(papers):
        if processed_dict is None or paper['url'] not in processed_dict:
            # New paper: generate time based on position (newest first)
            paper_time = base_time + timedelta(seconds=i)
            paper['pub_date'] = paper_time.strftime('%a, %d %b %Y %H:%M:%S GMT')
        else:
            # Cached paper: get pub_date from cache
            cached_paper = paper_cache.get(paper['url'])
            if cached_paper and 'pub_date' in cached_paper:
                paper['pub_date'] = cached_paper['pub_date']

    # Process paper details concurrently
    logger.info(f"📚 Processing {len(papers)} papers...")

    # Create ordered result list to maintain original order
    results = [None] * len(papers)
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # Submit all tasks and record their indices
        future_to_index = {executor.submit(process_paper, paper, processed_dict, paper_cache): i for i, paper in enumerate(papers)}        
        for future in as_completed(future_to_index):
            index = future_to_index[future]
            try:
                result = future.result()
                results[index] = result
                logger.info(f"[{index + 1}/{len(papers)}] Completed: {result['title'][:50]}")
            except Exception as e:
                paper = papers[index]
                logger.error(f"[{index + 1}/{len(papers)}] Failed: {paper['title'][:50]}: {e}")
                # Keep original data on failure
                results[index] = paper

    # Reverse order (newest first)
    results = results[::-1]
    
    logger.info(f"✅ Success: {len(results)}/{len(papers)}")
    return results

# ============= RSS Generation =============
def generate_rss(papers, request_url=None):
    """Generate RSS 2.0 Feed"""
    # Read configuration from environment variables, use defaults if not set
    if request_url is None:
        request_url = os.environ.get("RSS_FEED_URL", "https://your-username.github.io/hf-papers-rss/feed.xml")

    logger.info("📡 Generating RSS Feed...")
    logger.info("📋 Configuration:")
    logger.info(f"  - RSS Feed URL: {request_url}")
    logger.info(f"  - RSS Title: {os.environ.get('RSS_TITLE', 'Hugging Face Papers RSS')}")
    logger.info(f"  - RSS Description: {os.environ.get('RSS_DESCRIPTION', 'Latest AI research papers from Hugging Face')}")
    logger.info(f"  - Base URL: {BASE_URL}")
    logger.info(f"  - Max Papers: {MAX_PAPERS}")
    logger.info(f"  - Request Timeout: {REQUEST_TIMEOUT}s")
    logger.info(f"  - Max Retries: {MAX_RETRIES}")
    logger.info(f"  - Max Workers: {MAX_WORKERS}")
    logger.info(f"  - Target Languages: {TARGET_LANGUAGES}")

    rss = ET.Element("rss", {
        "version": "2.0",
        "xmlns:atom": "http://www.w3.org/2005/Atom"
    })

    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = os.environ.get("RSS_TITLE", "Hugging Face Papers RSS")
    ET.SubElement(channel, "link").text = BASE_URL
    ET.SubElement(channel, "description").text = os.environ.get("RSS_DESCRIPTION", "Latest AI research papers from Hugging Face")
    ET.SubElement(channel, "lastBuildDate").text = datetime.now(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S GMT')

    ET.SubElement(channel, "{http://www.w3.org/2005/Atom}link", {
        "href": request_url,
        "rel": "self",
        "type": "application/rss+xml"
    })

    for paper in papers:
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = paper['title']
        ET.SubElement(item, "link").text = paper['url']
        
        desc = ET.SubElement(item, "description")
        desc.text = f"<![CDATA[{paper['abstract_short']}]]>"
        
        abs_full = ET.SubElement(item, "abstractFull")
        abs_full.text = f"<![CDATA[{paper['abstract']}]]>"
        
        ET.SubElement(item, "pubDate").text = paper['pub_date']
        
        guid = ET.SubElement(item, "guid", {"isPermaLink": "true"})
        guid.text = paper['url']
        
        ET.SubElement(item, "institution").text = paper.get('institution', 'N/A')
        
        if paper.get('arxiv_abs'):
            ET.SubElement(item, "arxivAbs").text = paper['arxiv_abs']
        
        if paper.get('arxiv_pdf'):
            ET.SubElement(item, "arxivPdf").text = paper['arxiv_pdf']

    # Format XML
    xml_str = ET.tostring(rss, encoding='unicode')
    # Use manual formatting to avoid minidom XML declaration issues
    pretty_xml = '<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">\n'
    
    # Add channel
    pretty_xml += '  <channel>\n'
    pretty_xml += '    <title>Hugging Face Papers RSS</title>\n'
    pretty_xml += f'    <link>{BASE_URL}</link>\n'
    pretty_xml += '    <description>Latest AI research papers from Hugging Face</description>\n'
    pretty_xml += f'    <lastBuildDate>{datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")}</lastBuildDate>\n'
    pretty_xml += '    <atom:link href="{}" rel="self" type="application/rss+xml"/>\n'.format(request_url)
    
    # Add paper entries
    for paper in papers:
        pretty_xml += '    <item>\n'
        pretty_xml += f'      <title>{paper["title"]}</title>\n'
        pretty_xml += f'      <link>{paper["url"]}</link>\n'
        
        # Build structured HTML description
        description_html = '<div class="paper-content">\n'
        
        # Institution info (small text, no title)
        institution = paper.get('institution', 'N/A')
        institution_line = f"Institution: {institution}" if institution and institution != 'N/A' else ""
        
        # Author info (small text, follows institution info)
        authors = paper.get('authors', [])
        authors_line = f"Authors: {', '.join(authors[:5])}" if authors else ""
        
        # Combine institution and author info
        if institution_line or authors_line:
            parts = [p for p in [institution_line, authors_line] if p]
            description_html += f'  <p style="color: #666; font-size: 0.9em;">{" | ".join(parts)}</p>\n'
        
        # arXiv links
        arxiv_links = []
        if paper.get('arxiv_abs'):
            arxiv_links.append(f'<a href="{paper["arxiv_abs"]}">arXiv</a>')
        if paper.get('arxiv_pdf'):
            arxiv_links.append(f'<a href="{paper["arxiv_pdf"]}">PDF</a>')
        if arxiv_links:
            description_html += f'  <h3>arXiv Links</h3>\n'
            description_html += f'  <p>{" | ".join(arxiv_links)}</p>\n'
        
        # Short abstract
        description_html += f'  <h3>AI summary</h3>\n'
        description_html += f'  <p>{paper["abstract_short"]}</p>\n'

        # Translated content (placed after corresponding abstract)
        for lang in TARGET_LANGUAGES:
            desc_key = f'description_{lang}'
            abs_key = f'abstractFull_{lang}'
            
            # Short abstract translation
            if desc_key in paper and paper[desc_key] != paper["abstract_short"]:
                description_html += f'  <p>{paper[desc_key]}</p>\n'
        
        # Full abstract
        description_html += f'  <h3>Abstract</h3>\n'
        description_html += f'  <p>{paper["abstract"]}</p>\n'
        
        # Translated content (placed after corresponding abstract)
        for lang in TARGET_LANGUAGES:
            desc_key = f'description_{lang}'
            abs_key = f'abstractFull_{lang}'
            
            # Full abstract translation
            if abs_key in paper and paper[abs_key] != paper["abstract"]:
                description_html += f'  <p>{paper[abs_key]}</p>\n'
        
        description_html += '</div>'
        
        pretty_xml += f'      <description><![CDATA[{description_html}]]></description>\n'
        
        pretty_xml += f'      <pubDate>{paper["pub_date"]}</pubDate>\n'
        pretty_xml += f'      <guid isPermaLink="true">{paper["url"]}</guid>\n'
        pretty_xml += '    </item>\n'
    
    pretty_xml += '  </channel>\n'
    pretty_xml += '</rss>\n'
    
    logger.info(f"✅ Generated ({len(pretty_xml)} bytes)")
    return pretty_xml

def save_feed(content, filename):
    """Save RSS Feed to file"""
    logger.info(f"💾 Saving {filename}...")
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(content)
    logger.info(f"✅ Saved {filename}")

# ============= Main Function =============
def main():
    """Main function"""
    start = time.time()
    
    try:
        # Load processed papers list and complete cache
        processed_dict, paper_cache = load_processed_papers()
        
        papers = scrape_papers(processed_dict, paper_cache)
        if not papers:
            logger.error("No papers found!")
            return

        rss_feed = generate_rss(papers)
        save_feed(rss_feed, "docs/feed.xml")
        
        # Save processed papers list and complete cache
        save_processed_papers(papers, processed_dict, paper_cache)

        elapsed = time.time() - start
        logger.info("="*60)
        logger.info("📋 Summary:")
        logger.info(f"   Papers: {len(papers)}")
        logger.info(f"   Size: {len(rss_feed)} bytes")
        logger.info(f"   Time: {elapsed:.2f}s")
        logger.info(f"   Avg: {elapsed/len(papers):.2f}s/paper")
        logger.info("="*60)
        logger.info("🎉 Done!")

    except Exception as e:
        logger.error(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)

if __name__ == "__main__":
    main()