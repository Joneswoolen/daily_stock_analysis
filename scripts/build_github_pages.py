#!/usr/bin/env python3
"""
Build GitHub Pages static site from Markdown reports.

Reads all .md files from reports/ directory, converts them to HTML,
and generates an index page linking all historical reports.

Usage:
    python scripts/build_github_pages.py [--output-dir OUTPUT_DIR]
"""
import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

import markdown2


# ── HTML Templates ──────────────────────────────────────────────────────────

SITE_TITLE = "📊 A股自选股智能分析报告"

INDEX_CSS = """
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
    line-height: 1.6;
    color: #24292e;
    background: #f6f8fa;
    padding: 20px;
}
.container { max-width: 960px; margin: 0 auto; }
header {
    text-align: center;
    padding: 30px 0 20px;
    margin-bottom: 24px;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
    border-radius: 12px;
}
header h1 { font-size: 28px; margin-bottom: 6px; }
header p { opacity: 0.9; font-size: 14px; }
.stats {
    display: flex; gap: 16px; justify-content: center; margin-top: 16px;
}
.stats .stat {
    background: rgba(255,255,255,0.2); padding: 6px 16px; border-radius: 20px; font-size: 13px;
}
.report-list { list-style: none; }
.report-item {
    background: white;
    border-radius: 10px;
    padding: 16px 20px;
    margin-bottom: 12px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    text-decoration: none;
    color: #24292e;
    transition: box-shadow 0.2s, transform 0.1s;
    border: 1px solid #e1e4e8;
}
.report-item:hover {
    box-shadow: 0 4px 12px rgba(0,0,0,0.1);
    transform: translateY(-1px);
}
.report-date { font-size: 18px; font-weight: 600; color: #0366d6; }
.report-time { font-size: 12px; color: #6a737d; margin-top: 2px; }
.report-arrow { color: #0366d6; font-size: 20px; }
.empty-state {
    text-align: center; padding: 60px 20px; color: #6a737d;
}
.empty-state .emoji { font-size: 48px; margin-bottom: 16px; }
footer {
    text-align: center; margin-top: 40px; padding: 20px 0;
    color: #6a737d; font-size: 13px;
}
a { color: #0366d6; text-decoration: none; }
a:hover { text-decoration: underline; }
"""

REPORT_CSS = """
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
    line-height: 1.6;
    color: #24292e;
    font-size: 14px;
    padding: 20px;
    background: #f6f8fa;
}
.container { max-width: 900px; margin: 0 auto; }
.back-link {
    display: inline-flex; align-items: center; gap: 4px;
    color: #0366d6; font-size: 14px; margin-bottom: 16px;
    text-decoration: none; padding: 6px 12px;
    background: white; border-radius: 6px;
    border: 1px solid #e1e4e8;
}
.back-link:hover { text-decoration: none; background: #f1f8ff; }
.report-card {
    background: white;
    border-radius: 10px;
    padding: 24px 32px;
    border: 1px solid #e1e4e8;
}
h1 {
    font-size: 22px;
    border-bottom: 2px solid #eaecef;
    padding-bottom: 0.3em;
    margin-bottom: 1em;
    color: #0366d6;
}
h2 {
    font-size: 18px;
    border-bottom: 1px solid #eaecef;
    padding-bottom: 0.3em;
    margin-top: 1.5em;
    margin-bottom: 0.8em;
}
h3 {
    font-size: 16px;
    margin-top: 1.2em;
    margin-bottom: 0.4em;
}
p { margin-bottom: 10px; }
table {
    border-collapse: collapse;
    width: 100%;
    margin: 12px 0;
    display: block;
    overflow-x: auto;
    font-size: 13px;
}
th, td {
    border: 1px solid #dfe2e5;
    padding: 6px 10px;
    text-align: left;
}
th {
    background-color: #f6f8fa;
    font-weight: 600;
}
tr:nth-child(2n) { background-color: #f8f8f8; }
tr:hover { background-color: #f1f8ff; }
blockquote {
    color: #6a737d;
    border-left: 0.25em solid #dfe2e5;
    padding: 0 1em;
    margin: 0 0 10px 0;
}
code {
    padding: 0.2em 0.4em;
    margin: 0;
    font-size: 85%;
    background-color: rgba(27,31,35,0.05);
    border-radius: 3px;
    font-family: SFMono-Regular, Consolas, "Liberation Mono", Menlo, monospace;
}
pre {
    padding: 12px;
    overflow: auto;
    line-height: 1.45;
    background-color: #f6f8fa;
    border-radius: 3px;
    margin-bottom: 10px;
}
hr {
    height: 0.25em;
    padding: 0;
    margin: 16px 0;
    background-color: #e1e4e8;
    border: 0;
}
ul, ol { padding-left: 20px; margin-bottom: 10px; }
li { margin: 2px 0; }
.report-footer {
    text-align: center; margin-top: 24px; color: #6a737d; font-size: 12px;
}
"""


# ── Helpers ─────────────────────────────────────────────────────────────────

def parse_report_metadata(md_text: str) -> dict:
    """Extract date and summary info from the first few lines of a report."""
    meta = {"date": "", "time": "", "title": "", "summary": ""}
    lines = md_text.strip().split("\n")
    if lines:
        # First line usually: # 🎯 2026-03-30 ... or similar
        title_match = re.search(r"(\d{4}-\d{2}-\d{2})", lines[0])
        if title_match:
            meta["date"] = title_match.group(1)
            meta["title"] = lines[0].lstrip("# ").strip()
    # Look for summary line with stock counts
    for line in lines[:5]:
        if "🟢" in line or "自选股" in line or "stock" in line.lower():
            meta["summary"] = line.strip().lstrip(">").strip()
            break
    return meta


def build_index_html(reports: list[dict]) -> str:
    """Build the index page HTML."""
    if not reports:
        report_items = """
            <div class="empty-state">
                <div class="emoji">📭</div>
                <p>暂无分析报告</p>
                <p style="font-size:13px;margin-top:8px;">报告将在每次自动分析后自动生成</p>
            </div>
        """
    else:
        items = []
        for r in reports:
            items.append(f"""
            <li>
                <a class="report-item" href="{r['html_file']}">
                    <div>
                        <div class="report-date">{r['date']}</div>
                        <div class="report-time">{r['title']}</div>
                    </div>
                    <div class="report-arrow">→</div>
                </a>
            </li>""")
        report_items = "\n".join(items)

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{SITE_TITLE}</title>
    <style>{INDEX_CSS}</style>
</head>
<body>
<div class="container">
    <header>
        <h1>{SITE_TITLE}</h1>
        <p>每日自动分析 · 智能推送</p>
        <div class="stats">
            <span class="stat">📊 共 {len(reports)} 份报告</span>
            <span class="stat">🕐 最近更新：{reports[0]['date'] if reports else '暂无'}</span>
        </div>
    </header>

    <main>
        <ul class="report-list">
            {report_items}
        </ul>
    </main>

    <footer>
        Powered by <a href="https://github.com/Joneswoolen/daily_stock_analysis">daily_stock_analysis</a>
        · 数据仅供参考，不构成投资建议
    </footer>
</div>
</body>
</html>"""


def build_report_html(md_content: str, filename: str) -> str:
    """Convert a single markdown report to a full HTML page."""
    html_body = markdown2.markdown(
        md_content,
        extras=["tables", "fenced-code-blocks", "break-on-newline", "cuddled-lists"],
    )
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>分析报告 - {filename}</title>
    <style>{REPORT_CSS}</style>
</head>
<body>
<div class="container">
    <a class="back-link" href="index.html">← 返回报告列表</a>
    <div class="report-card">
        {html_body}
    </div>
    <div class="report-footer">
        Powered by <a href="https://github.com/Joneswoolen/daily_stock_analysis">daily_stock_analysis</a>
        · 数据仅供参考，不构成投资建议
    </div>
</div>
</body>
</html>"""


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Build GitHub Pages from reports")
    parser.add_argument("--reports-dir", default=None, help="Path to reports directory")
    parser.add_argument("--output-dir", default=None, help="Path to output directory")
    args = parser.parse_args()

    project_root = Path(__file__).parent.parent
    reports_dir = Path(args.reports_dir) if args.reports_dir else project_root / "reports"
    output_dir = Path(args.output_dir) if args.output_dir else project_root / "gh-pages-content"

    output_dir.mkdir(parents=True, exist_ok=True)

    # Find all .md report files
    md_files = sorted(reports_dir.glob("report_*.md"), reverse=True)
    print(f"Found {len(md_files)} report(s) in {reports_dir}")

    reports_meta = []

    for md_file in md_files:
        md_content = md_file.read_text(encoding="utf-8")
        if not md_content.strip():
            continue

        meta = parse_report_metadata(md_content)
        html_filename = md_file.stem + ".html"

        # Write individual HTML report
        html_content = build_report_html(md_content, md_file.name)
        (output_dir / html_filename).write_text(html_content, encoding="utf-8")

        reports_meta.append({
            "date": meta["date"] or md_file.stem.replace("report_", ""),
            "title": meta["title"] or md_file.name,
            "html_file": html_filename,
        })
        print(f"  ✓ {html_filename}")

    # Build and write index page
    index_html = build_index_html(reports_meta)
    (output_dir / "index.html").write_text(index_html, encoding="utf-8")
    print(f"\nIndex page: {output_dir / 'index.html'}")
    print(f"Total: {len(reports_meta)} report(s) converted")


if __name__ == "__main__":
    main()
