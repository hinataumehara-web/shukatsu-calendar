#!/usr/bin/env python3
"""就活サイトのエントリー締切を Google Calendar に自動登録する

使い方:
    python3 main.py                    # 有効な全サイトを巡回して同期
    python3 main.py --dry-run          # カレンダーに書き込まず、検出結果だけ表示
    python3 main.py --site type_shukatsu   # 特定サイトだけ実行
    python3 main.py --list-sites       # サイト定義の一覧を表示
"""
import argparse
import asyncio
import logging
import os
import sys
from datetime import date

import yaml

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from engine.calendar_client import CalendarClient          # noqa: E402
from engine.site_config import SiteConfigError, load_site_configs  # noqa: E402

logger = logging.getLogger("shukatsu")


def setup_logging(log_file: str | None):
    handlers = [logging.StreamHandler(sys.stdout)]
    if log_file:
        handlers.append(logging.FileHandler(os.path.join(BASE_DIR, log_file)))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=handlers,
    )


def load_config(path: str | None = None) -> dict:
    path = path or os.path.join(BASE_DIR, "config.yaml")
    if not os.path.exists(path):
        raise SystemExit(
            f"{path} がありません。config.example.yaml をコピーして作成してください:\n"
            f"    cp config.example.yaml config.yaml"
        )
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_dotenv(path: str | None = None):
    """依存を増やさないための最小限の .env ローダ（既存の環境変数を優先）"""
    path = path or os.path.join(BASE_DIR, ".env")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


async def run_site(site, settings: dict):
    """1サイトを巡回して締切リストを返す"""
    from playwright.async_api import async_playwright

    from engine.scraper import GenericScraper

    entries = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=settings.get("headless", True))
        context = await browser.new_context(user_agent=settings.get("user_agent") or (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ))
        page = await context.new_page()
        scraper = GenericScraper(site, page, settings)
        try:
            await scraper.login()
            found = await scraper.collect()
            days_ahead = settings.get("days_ahead", 90)
            today = date.today()
            entries = [
                e for e in found
                if today <= e.deadline and (e.deadline - today).days <= days_ahead
            ]
            logger.info(f"{site.name}: 期間内 {len(entries)} 件 / 検出 {len(found)} 件")
        except Exception as e:
            logger.error(f"{site.name}: 処理中にエラー: {e}", exc_info=True)
        finally:
            await browser.close()
    return entries


async def main_async(args):
    config = load_config(args.config)
    settings = config.get("settings", {})
    calendar_config = config.get("google_calendar", {})

    sites = load_site_configs(os.path.join(BASE_DIR, "sites"))

    if args.list_sites:
        for s in sites:
            state = "有効" if s.enabled else "無効"
            print(f"  {s.slug:<24} {s.name:<24} [{state}] 一覧 {len(s.listings)} ページ")
        return 0

    targets = [s for s in sites if (s.slug in args.site) or (not args.site and s.enabled)]
    if not targets:
        logger.error("実行対象のサイトがありません（--list-sites で確認してください）")
        return 1

    cal = None
    if not args.dry_run:
        cal = CalendarClient(calendar_config, base_dir=BASE_DIR)
        cal.authenticate()

    all_entries = []
    for site in targets:
        logger.info(f"=== {site.name} 開始 ===")
        all_entries.extend(await run_site(site, settings))

    logger.info(f"合計 {len(all_entries)} 件の締切を検出")
    if not all_entries:
        return 0

    if args.dry_run:
        for e in sorted(all_entries, key=lambda x: x.deadline):
            print(f"  {e.deadline}  [{e.source}] {e.company} / {e.event_title}")
        logger.info("dry-run のためカレンダーには書き込みませんでした")
        return 0

    added, skipped = cal.sync(all_entries, settings.get("days_ahead", 90))
    logger.info(f"同期完了: {added} 件追加, {skipped} 件スキップ（重複）")
    return 0


def main():
    parser = argparse.ArgumentParser(description="就活サイトの締切を Google Calendar に同期する")
    parser.add_argument("--config", help="設定ファイルのパス（既定: config.yaml）")
    parser.add_argument("--site", action="append", default=[],
                        help="実行するサイトの slug（sites/<slug>.yaml）。複数指定可")
    parser.add_argument("--dry-run", action="store_true",
                        help="カレンダーに書き込まず、検出した締切を表示するだけ")
    parser.add_argument("--list-sites", action="store_true", help="サイト定義の一覧を表示")
    args = parser.parse_args()

    load_dotenv()
    config_for_log = {}
    try:
        config_for_log = load_config(args.config)
    except SystemExit:
        pass
    setup_logging(config_for_log.get("settings", {}).get("log_file", "shukatsu.log"))

    try:
        return asyncio.run(main_async(args))
    except SiteConfigError as e:
        logger.error(f"サイト定義エラー: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
