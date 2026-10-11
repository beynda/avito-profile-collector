from __future__ import annotations
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import yaml
import math
import re

def validate_config(raw):
    if not isinstance(raw, dict):
        raise ValueError('Configuration must be a YAML mapping.')
    if set(raw) - {'keywords', 'regions', 'delays', 'browser', 'output', 'database', 'proxy', 'max_pages_per_query'}:
        raise ValueError('Unknown configuration section.')
    def text(value, label):
        if not isinstance(value, str) or not value.strip() or '\x00' in value:
            raise ValueError(f'{label} must be a non-empty string.')
    keywords = raw.get('keywords')
    if not isinstance(keywords, list) or not keywords:
        raise ValueError('keywords must be a non-empty list.')
    for keyword in keywords:
        text(keyword, 'keyword')
    regions = raw.get('regions')
    if not isinstance(regions, list) or not regions:
        raise ValueError('regions must be a non-empty list.')
    for region in regions:
        if not isinstance(region, dict) or set(region) != {'slug', 'name'}:
            raise ValueError('Each region requires slug and name.')
        text(region['name'], 'region name')
        text(region['slug'], 'region slug')
        if not re.fullmatch(r'[a-z0-9_-]+(?:/[a-z0-9_-]+)*', region['slug']):
            raise ValueError('Region slug must be an Avito relative path, without URL or query parameters.')
    limit = raw.get('max_pages_per_query', 0)
    if type(limit) is not int or limit < 0:
        raise ValueError('max_pages_per_query must be a non-negative integer.')
    sections = {'browser': {'headless', 'user_data_dir'}, 'output': {'excel_path', 'csv_path'}, 'database': {'path'}, 'delays': set(Delays.__dataclass_fields__)}
    for name, keys in sections.items():
        section = raw.get(name, {})
        if not isinstance(section, dict) or set(section) - keys:
            raise ValueError(f'Invalid {name} section or unknown option.')
        for key, value in section.items():
            if name == 'delays':
                if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                    raise ValueError('Delays must be finite non-negative numbers.')
            elif key == 'headless':
                if type(value) is not bool:
                    raise ValueError('browser.headless must be true or false.')
            else:
                text(value, f'{name}.{key}')
    if 'path' not in raw.get('database', {}):
        raise ValueError('database.path is required.')
    output = OutputConfig(**raw.get('output', {}))
    paths = [Path(value).resolve() for value in (raw['database']['path'], output.excel_path, output.csv_path)]
    if len(set(paths)) != len(paths):
        raise ValueError('Database, Excel and CSV must use different file paths.')
    delays = Delays(**raw.get('delays', {}))
    for prefix in ('between_listings', 'between_pages', 'between_queries'):
        if getattr(delays, prefix + '_min') > getattr(delays, prefix + '_max'):
            raise ValueError('Minimum delay must not exceed maximum delay.')
    proxy = raw.get('proxy')
    if proxy is not None:
        if not isinstance(proxy, dict) or 'server' not in proxy or set(proxy) - {'server', 'username', 'password', 'bypass'}:
            raise ValueError('Invalid proxy configuration.')
        for key, value in proxy.items():
            text(value, 'proxy.' + key)

@dataclass
class Region:
    slug: str
    name: str

@dataclass
class Delays:
    between_listings_min: float = 3
    between_listings_max: float = 7
    between_pages_min: float = 5
    between_pages_max: float = 10
    between_queries_min: float = 8
    between_queries_max: float = 15

    def listing(self) -> float:
        return random.uniform(self.between_listings_min, self.between_listings_max)

    def page(self) -> float:
        return random.uniform(self.between_pages_min, self.between_pages_max)

    def query(self) -> float:
        return random.uniform(self.between_queries_min, self.between_queries_max)

@dataclass
class BrowserConfig:
    headless: bool = False
    user_data_dir: str = 'data/browser_profile'

@dataclass
class OutputConfig:
    excel_path: str = 'data/output.xlsx'
    csv_path: str = 'data/output.csv'

@dataclass
class Config:
    keywords: list[str]
    regions: list[Region]
    delays: Delays
    max_pages_per_query: int
    browser: BrowserConfig
    proxy: Optional[dict]
    output: OutputConfig
    db_path: str
    base_dir: Path = field(default_factory=Path.cwd)

    def resolve(self, rel_path: str) -> Path:
        p = Path(rel_path)
        if p.is_absolute():
            return p
        return self.base_dir / p

def load_config(path: str='config.yaml') -> Config:
    cfg_path = Path(path)
    base_dir = cfg_path.resolve().parent
    with open(cfg_path, 'r', encoding='utf-8') as f:
        raw = yaml.safe_load(f)
    validate_config(raw)
    regions = [Region(slug=r['slug'], name=r['name']) for r in raw['regions']]
    delays = Delays(**raw.get('delays', {}))
    browser = BrowserConfig(**raw.get('browser', {}))
    output = OutputConfig(**raw.get('output', {}))
    cfg = Config(keywords=raw['keywords'], regions=regions, delays=delays, max_pages_per_query=raw.get('max_pages_per_query', 0), browser=browser, proxy=raw.get('proxy'), output=output, db_path=raw['database']['path'], base_dir=base_dir)
    return cfg
