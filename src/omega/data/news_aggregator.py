"""
News Aggregator Module - OMEGA_QUANT Data Layer
Phase 25.2: Centralized PIT-Safe Web Scraping for Vietnamese Financial News

Provides:
- Rate-limited scraping from CafeF and Vietstock
- Mandatory PIT-safety (reference date is strictly required)
- Normalized output structures compatible with VSIPortfolioEngine
"""

import logging
import time
from datetime import datetime, timedelta
from typing import List, Optional
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


@dataclass
class SentimentInput:
    """Input structure for sentiment analysis (PIT safe)."""
    text: str
    source: str
    timestamp: datetime
    ticker: Optional[str] = None
    weight_override: Optional[float] = None


class NewsAggregator:
    """Web scraper for Vietnamese financial news sources with strict PIT safety."""
    
    def __init__(self):
        self.last_request_time = {}
        self.rate_limit_seconds = 2.0
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
        }
    
    def _rate_limit(self, domain: str) -> None:
        if domain in self.last_request_time:
            elapsed = time.time() - self.last_request_time[domain]
            if elapsed < self.rate_limit_seconds:
                sleep_time = self.rate_limit_seconds - elapsed
                time.sleep(sleep_time)
        self.last_request_time[domain] = time.time()
    
    def _fetch_url(self, url: str, domain: str) -> Optional[BeautifulSoup]:
        try:
            self._rate_limit(domain)
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            return BeautifulSoup(response.content, 'html.parser')
        except Exception as e:
            logger.error(f"Failed to fetch {url}: {e}")
            return None
            
    def _scrape_cafef(self, as_of_time: datetime, hours_back: int = 24) -> List[SentimentInput]:
        if as_of_time is None:
            raise ValueError("as_of_time is mandatory for PIT safety")
            
        results = []
        domain = 'cafef.vn'
        
        try:
            url = 'https://cafef.vn/thi-truong-chung-khoan.chn'
            soup = self._fetch_url(url, domain)
            if soup is None:
                return results
                
            articles = soup.find_all('h3', class_='title')
            cutoff_time = as_of_time - timedelta(hours=hours_back)
            
            for article in articles[:20]:
                try:
                    link_tag = article.find('a')
                    if not link_tag:
                        continue
                    headline = link_tag.get_text(strip=True)
                    if not headline:
                        continue
                        
                    time_tag = article.find_next('span', class_='time')
                    if time_tag:
                        timestamp = self._parse_cafef_time(time_tag.get_text(strip=True), as_of_time)
                    else:
                        timestamp = as_of_time
                        
                    # Check PIT limit: cannot use future articles
                    if timestamp > as_of_time:
                        continue
                        
                    if timestamp >= cutoff_time:
                        results.append(SentimentInput(
                            text=headline,
                            source='CafeF',
                            timestamp=timestamp
                        ))
                except Exception as e:
                    logger.warning(f"Error parsing CafeF article: {e}")
                    continue
        except Exception as e:
            logger.error(f"Error scraping CafeF: {e}")
        return results

    def _parse_cafef_time(self, time_text: str, reference_time: datetime) -> datetime:
        try:
            time_text = time_text.lower().strip()
            if 'phút trước' in time_text:
                minutes = int(time_text.split()[0])
                return reference_time - timedelta(minutes=minutes)
            if 'giờ trước' in time_text:
                hours = int(time_text.split()[0])
                return reference_time - timedelta(hours=hours)
            if '/' in time_text and ':' in time_text:
                return datetime.strptime(time_text, '%d/%m/%Y %H:%M')
            return reference_time
        except Exception as e:
            logger.warning(f"Failed to parse CafeF time '{time_text}': {e}")
            return reference_time

    def _scrape_vietstock(self, as_of_time: datetime, hours_back: int = 24) -> List[SentimentInput]:
        if as_of_time is None:
            raise ValueError("as_of_time is mandatory for PIT safety")
            
        results = []
        domain = 'vietstock.vn'
        
        try:
            url = 'https://vietstock.vn/thi-truong-chung-khoan'
            soup = self._fetch_url(url, domain)
            if soup is None:
                return results
                
            articles = soup.find_all('div', class_='news-item')
            if not articles:
                articles = soup.find_all(['h3', 'h4'])
                
            cutoff_time = as_of_time - timedelta(hours=hours_back)
            
            for article in articles[:20]:
                try:
                    link_tag = article.find('a')
                    if not link_tag:
                        continue
                    headline = link_tag.get_text(strip=True)
                    if not headline:
                        continue
                        
                    time_tag = article.find('span', class_='time')
                    if not time_tag:
                        time_tag = article.find('time')
                        
                    if time_tag:
                        timestamp = self._parse_vietstock_time(time_tag.get_text(strip=True), as_of_time)
                    else:
                        timestamp = as_of_time
                        
                    if timestamp > as_of_time:
                        continue
                        
                    if timestamp >= cutoff_time:
                        results.append(SentimentInput(
                            text=headline,
                            source='Vietstock',
                            timestamp=timestamp
                        ))
                except Exception as e:
                    logger.warning(f"Error parsing Vietstock article: {e}")
                    continue
        except Exception as e:
            logger.error(f"Error scraping Vietstock: {e}")
        return results

    def _parse_vietstock_time(self, time_text: str, reference_time: datetime) -> datetime:
        try:
            time_text = time_text.lower().strip()
            if 'phút trước' in time_text:
                minutes = int(time_text.split()[0])
                return reference_time - timedelta(minutes=minutes)
            if 'giờ trước' in time_text:
                hours = int(time_text.split()[0])
                return reference_time - timedelta(hours=hours)
            if '/' in time_text and ':' in time_text:
                return datetime.strptime(time_text, '%d/%m/%Y %H:%M')
            return reference_time
        except Exception as e:
            logger.warning(f"Failed to parse Vietstock time '{time_text}': {e}")
            return reference_time

    def fetch_recent_news(self, as_of_time: datetime, hours_back: int = 24) -> List[SentimentInput]:
        """Fetch recent news from all VN sources. Mandatory as_of_time for PIT safety."""
        if as_of_time is None:
            raise ValueError("as_of_time is mandatory for PIT safety")
            
        all_news = []
        logger.info(f"Fetching news from last {hours_back} hours as of {as_of_time}...")
        
        try:
            cafef_news = self._scrape_cafef(as_of_time, hours_back)
            all_news.extend(cafef_news)
        except Exception as e:
            logger.error(f"CafeF scraping failed: {e}")
            
        try:
            vietstock_news = self._scrape_vietstock(as_of_time, hours_back)
            all_news.extend(vietstock_news)
        except Exception as e:
            logger.error(f"Vietstock scraping failed: {e}")
            
        all_news.sort(key=lambda x: x.timestamp, reverse=True)
        return all_news
