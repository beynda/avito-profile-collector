from __future__ import annotations
import logging
import random
import re
import time
import sys
from dataclasses import dataclass
from typing import Optional
from urllib.parse import quote, urljoin
from playwright.sync_api import BrowserContext, Page, TimeoutError as PWTimeout
from .config import Config, Region
from .db import Database, ProfileRecord
from . import control
BASE_URL = 'https://www.avito.ru'
SELECTORS = {'search_item': ['[data-marker="item"]', 'div[data-marker^="item"]', 'article'], 'search_item_link': ['a[data-marker="item-title"]', 'a[itemprop="url"]', 'a[href^="/"]'], 'next_page': ['a[data-marker="pagination-button/nextPage"]', 'a[data-marker="pagination-button/next"]', 'a[aria-label="Следующая страница"]'], 'seller_link': ['a[data-marker="seller-link/link"]', 'a[data-marker="seller-info/name"]', 'a[href*="/user/"]', 'a[href*="/brands/"]'], 'seller_name': ['[data-marker="seller-info/name"]', '[data-marker="seller-link/name"]', 'h1[data-marker="seller-info/name"]'], 'item_address': ['[data-marker="item-view/item-address"]', '[itemprop="address"]', '[data-marker="item-view/address"]'], 'item_title': ['h1[data-marker="item-view/title-info"]', 'h1[itemprop="name"]', 'h1'], 'profile_name': ['[data-marker="page-title/text"]', '[data-marker="seller-info/name"]', 'h1'], 'profile_address': ['[data-marker="seller-info/address"]', '[itemprop="address"]'], 'profile_description': ['[data-marker="seller-info/description"]', '[data-marker="about-seller/description"]']}

def first_match_text(page: Page, selector_key: str) -> str:
    for sel in SELECTORS[selector_key]:
        try:
            el = page.locator(sel).first
            if el.count() > 0:
                text = el.inner_text(timeout=2000).strip()
                if text:
                    return text
        except Exception:
            continue
    return ''

def first_match_href(page: Page, selector_key: str) -> str:
    for sel in SELECTORS[selector_key]:
        try:
            el = page.locator(sel).first
            if el.count() > 0:
                href = el.get_attribute('href')
                if href:
                    return href
        except Exception:
            continue
    return ''
EMAIL_RE = re.compile('[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}')

def extract_email_from_text(text: str) -> str:
    m = EMAIL_RE.search(text or '')
    return m.group(0) if m else ''
WHITESPACE_RE = re.compile('\\s+')

def clean_text(value: str) -> str:
    if not value:
        return ''
    return WHITESPACE_RE.sub(' ', value.replace('\xa0', ' ')).strip()

def extract_name_from_title(title: str) -> str:
    if not title:
        return ''
    name = title.split(' - официальная страница')[0].strip()
    if name and name.lower() not in ('авито', 'авито - объявления на сайте авито'):
        return name
    return ''

def extract_profile_id(profile_url: str) -> str:
    m = re.search('/user/([a-f0-9\\-]+)', profile_url)
    if m:
        return m.group(1)
    m = re.search('/brands/[^/]*-(\\d+)', profile_url)
    if m:
        return m.group(1)
    return profile_url.split('?')[0].rstrip('/')

def build_search_url(region: Region, query: str, page_num: int) -> str:
    q = quote(query)
    url = f'{BASE_URL}/{region.slug}?q={q}&localPriority=1'
    if page_num > 1:
        url += f'&p={page_num}'
    return url

def sleep_delay(seconds: float, logger: logging.Logger, reason: str=''):
    logger.debug(f'Waiting {seconds:.1f} seconds. {reason}')
    control.sleep(seconds)

@dataclass
class ScrapeStats:
    listings_seen: int = 0
    listings_new: int = 0
    profiles_new: int = 0
    profiles_seen_repeat: int = 0
    errors: int = 0

def collect_listing_links(page: Page, logger: logging.Logger) -> list[str]:
    links: list[str] = []
    for sel in SELECTORS['search_item']:
        items = page.locator(sel)
        count = items.count()
        if count == 0:
            continue
        for i in range(count):
            item = items.nth(i)
            href = ''
            for link_sel in SELECTORS['search_item_link']:
                try:
                    link_el = item.locator(link_sel).first
                    if link_el.count() > 0:
                        href = link_el.get_attribute('href') or ''
                        if href:
                            break
                except Exception:
                    continue
            if href:
                full = urljoin(BASE_URL, href.split('?')[0])
                if full not in links:
                    links.append(full)
        if links:
            break
    return links

def has_next_page(page: Page) -> bool:
    for sel in SELECTORS['next_page']:
        try:
            el = page.locator(sel).first
            if el.count() > 0 and el.is_enabled():
                return True
        except Exception:
            continue
    return False

def looks_like_captcha_or_block(page: Page) -> bool:
    try:
        text = page.locator('body').inner_text(timeout=2000).lower()
    except Exception:
        return False
    markers = ['доступ ограничен', 'подтвердите, что вы не робот', 'access denied', 'проблема с ip']
    return any((m in text for m in markers))

def wait_for_manual_verification(page: Page, logger: logging.Logger) -> bool:
    if not looks_like_captcha_or_block(page):
        return True
    if not getattr(page.context, '_manual_verification_enabled', False) or not sys.stdin.isatty():
        return False
    while looks_like_captcha_or_block(page):
        logger.warning('Collection paused. Complete verification manually in this browser tab. Keep the tab open.')
        try:
            control.waiting_for_input = True
            answer = control.prompt('After the page loads normally, press Enter here to continue, or type q to stop this attempt: ')
        except EOFError:
            return False
        finally:
            control.waiting_for_input = False
        control.checkpoint()
        if answer.strip().lower() == 'q':
            return False
        if page.is_closed():
            logger.warning('Verification tab was closed.')
            return False
        page.wait_for_timeout(500)
    logger.info('Verification cleared; continuing collection in the same tab.')
    return True

def scrape_listing_and_profile(context: BrowserContext, listing_url: str, query: str, region: Region, db: Database, logger: logging.Logger, stats: ScrapeStats) -> bool:
    control.checkpoint()
    logger.info(f'Opening listing: {listing_url}')
    page = context.new_page()
    try:
        page.goto(listing_url, timeout=30000, wait_until='domcontentloaded')
        if not wait_for_manual_verification(page, logger):
            stats.errors += 1
            logger.warning('Listing is blocked; retry after manual browser verification.')
            return False
        seller_href = ''
        for attempt in range(2):
            try:
                page.wait_for_selector(','.join(SELECTORS['seller_link']), timeout=10000)
            except PWTimeout:
                pass
            page.wait_for_timeout(400)
            if not wait_for_manual_verification(page, logger):
                stats.errors += 1
                return False
            seller_href = first_match_href(page, 'seller_link')
            if seller_href:
                break
            logger.info(f'Seller not found at {listing_url}; reloading (attempt {attempt + 1}/3).')
            page.reload(timeout=30000, wait_until='domcontentloaded')
        listing_title = first_match_text(page, 'item_title')
        item_address_text = first_match_text(page, 'item_address')
        if not seller_href:
            logger.warning(f'Seller profile not found for {listing_url}')
            stats.errors += 1
            return False
        profile_url = urljoin(BASE_URL, seller_href.split('?')[0])
        profile_id = extract_profile_id(profile_url)
        if db.profile_exists(profile_id):
            existing = db.get_profile(profile_id)
            existing_name = existing['name'] if existing else profile_id
            logger.info(f'Existing profile: {existing_name} ({profile_url}), found via {listing_url}')
            rec = ProfileRecord(profile_id=profile_id, profile_url=profile_url, name='', city='', address='', email='', listing_url=listing_url, listing_title=listing_title, query=query)
            db.upsert_profile(rec)
            stats.profiles_seen_repeat += 1
            return True
        profile_page = context.new_page()
        try:
            profile_page.goto(profile_url, timeout=30000, wait_until='domcontentloaded')
            if not wait_for_manual_verification(profile_page, logger):
                stats.errors += 1
                logger.warning('Profile is blocked; no data saved.')
                return False
            try:
                profile_page.wait_for_selector(','.join(SELECTORS['profile_name']), timeout=6000)
            except PWTimeout:
                pass
            profile_page.wait_for_timeout(400)
            if not wait_for_manual_verification(profile_page, logger):
                stats.errors += 1
                return False
            name = ''
            for _ in range(2):
                name = first_match_text(profile_page, 'profile_name') or first_match_text(page, 'seller_name')
                if name:
                    break
                profile_page.wait_for_timeout(500)
            if not name:
                name = extract_name_from_title(profile_page.title())
            if not name or looks_like_captcha_or_block(profile_page):
                stats.errors += 1
                return False
            address = first_match_text(profile_page, 'profile_address') or item_address_text
            description = first_match_text(profile_page, 'profile_description')
            try:
                visible_text = profile_page.locator('body').inner_text(timeout=2000)
            except Exception:
                visible_text = ''
            email = extract_email_from_text(visible_text) or extract_email_from_text(description)
            city = region.name
            if address:
                parts = [p.strip() for p in address.replace('\n', ',').split(',') if p.strip()]
                for part in parts:
                    lowered = part.lower()
                    if lowered.startswith('р-н') or 'обл.' in lowered or 'область' in lowered:
                        continue
                    city = part
                    break
        finally:
            profile_page.close()
        rec = ProfileRecord(profile_id=profile_id, profile_url=profile_url, name=clean_text(name), city=clean_text(city), address=clean_text(address), email=email or '', listing_url=listing_url, listing_title=clean_text(listing_title), query=query, description=clean_text(description))
        db.upsert_profile(rec)
        stats.profiles_new += 1
        logger.info(f'New profile: {name or profile_id} ({profile_url})')
        return True
    except PWTimeout:
        logger.warning(f'Listing loading timed out: {listing_url}')
        stats.errors += 1
        return False
    except Exception as e:
        logger.warning(f'Listing processing failed at {listing_url}: {e}')
        stats.errors += 1
        return False
    finally:
        page.close()

def run_scrape(context: BrowserContext, cfg: Config, db: Database, logger: logging.Logger):
    overall = ScrapeStats()
    for query in cfg.keywords:
        for region in cfg.regions:
            control.checkpoint()
            if db.query_region_done(query, region.slug):
                logger.info(f'Query "{query}" / region "{region.name}" already completed; skipping.')
                continue
            logger.info(f'Query "{query}" / region "{region.name}"')
            page_num = 1
            query_listings_found = 0
            query_completed = False
            query_failed = False
            search_page = context.new_page()
            try:
                while True:
                    control.checkpoint()
                    if cfg.max_pages_per_query and page_num > cfg.max_pages_per_query:
                        break
                    url = build_search_url(region, query, page_num)
                    try:
                        search_page.goto(url, timeout=30000, wait_until='domcontentloaded')
                        try:
                            search_page.wait_for_selector(','.join(SELECTORS['search_item']), timeout=8000)
                        except PWTimeout:
                            pass
                        search_page.wait_for_timeout(500)
                    except PWTimeout:
                        logger.warning(f'Search loading timed out: {url}')
                        overall.errors += 1
                        query_failed = True
                        break
                    if not wait_for_manual_verification(search_page, logger):
                        overall.errors += 1
                        query_failed = True
                        logger.warning('Search is blocked; query remains pending.')
                        break
                    links = collect_listing_links(search_page, logger)
                    if not links:
                        logger.info(f'Page {page_num}: no listings found; stopping query.')
                        break
                    logger.info(f'Page {page_num}: found {len(links)} listings.')
                    query_listings_found += len(links)
                    overall.listings_seen += len(links)
                    for listing_url in links:
                        if db.is_listing_processed(listing_url):
                            logger.info(f'Previously processed; skipping: {listing_url}')
                            continue
                        if '/predlozheniya_uslug/' not in listing_url:
                            logger.info(f'Skipping non-service listing: {listing_url}')
                            db.mark_listing_processed(listing_url, query, region.slug)
                            continue
                        overall.listings_new += 1
                        ok = scrape_listing_and_profile(context, listing_url, query, region, db, logger, overall)
                        if ok:
                            db.mark_listing_processed(listing_url, query, region.slug)
                        else:
                            query_failed = True
                        sleep_delay(cfg.delays.listing(), logger, 'between listings')
                    if not has_next_page(search_page):
                        query_completed = not query_failed
                        break
                    page_num += 1
                    sleep_delay(cfg.delays.page(), logger, 'between search pages')
            finally:
                search_page.close()
            db.log_run_stats(query, region.slug, query_listings_found)
            if query_completed:
                db.mark_query_complete(query, region.slug)
            logger.info(f'Query "{query}" / "{region.name}": {query_listings_found} listings viewed.')
            sleep_delay(cfg.delays.query(), logger, 'between queries')
    logger.info(f'Finished. Viewed: {overall.listings_seen}; processed new listings: {overall.listings_new}; new profiles: {overall.profiles_new}; repeated profiles: {overall.profiles_seen_repeat}; errors: {overall.errors}; total saved profiles: {db.count_profiles()}.')
    return overall
