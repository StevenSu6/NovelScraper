import os  # 新增引入 os 模組
import json  # 新增引入 json 模組
import cloudscraper
from bs4 import BeautifulSoup

class ScraperFactory:
    @staticmethod
    def get_scraper(scraper_type):
        if scraper_type == "czbooks":
            return CzbooksScraper()
        elif scraper_type == "ttkan":
            return TtkanScraper()  # 新增對 ttkan 的支援
        elif scraper_type == "other":
            return OtherScraper()
        else:
            raise ValueError(f"Unknown scraper type: {scraper_type}")

class CzbooksScraper:
    def __init__(self):
        self.base_url = 'https://czbooks.net/n/'

    def load_chapters(self, novel_code):
        chapters_file = f'{novel_code}/chapters.json'
        if os.path.exists(chapters_file):
            with open(chapters_file, 'r', encoding='utf-8') as file:
                return json.load(file)
        return {}

    def scrape_chapters(self, novel_code):
        novel_url = f'{self.base_url}{novel_code}'
        scraper = cloudscraper.create_scraper()
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-TW,zh;q=0.8,en-US;q=0.5,en;q=0.3',
            'Referer': 'https://czbooks.net/'
        }
        response = scraper.get(novel_url, headers=headers)
        if response.status_code != 200:
            messagebox.showerror('Error', f'Failed to load chapters: {response.status_code}')
            return {}
        soup = BeautifulSoup(response.content, 'html.parser')
        chapters = {}
        for li in soup.select('ul.nav.chapter-list li'):
            a = li.find('a')
            if a:
                chapter_name = a.text.strip()
                chapter_url = a['href']
                if chapter_url.startswith('//'):
                    chapter_url = 'https:' + chapter_url
                chapters[chapter_name] = chapter_url
        self.save_chapters(novel_code, chapters)
        return chapters

    def scrape_novel_title(self, novel_code):
        novel_url = f'{self.base_url}{novel_code}'
        scraper = cloudscraper.create_scraper()
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-TW,zh;q=0.8,en-US;q=0.5,en;q=0.3',
            'Referer': 'https://czbooks.net/'
        }
        response = scraper.get(novel_url, headers=headers)
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            info_div = soup.find('div', class_='info')
            if info_div:
                title_span = info_div.find('span', class_='title')
                if title_span:
                    return title_span.get_text(strip=True)
        return None

    def save_chapters(self, novel_code, chapters):
        os.makedirs(novel_code, exist_ok=True)
        chapters_file = f'{novel_code}/chapters.json'
        with open(chapters_file, 'w', encoding='utf-8') as file:
            json.dump(chapters, file, ensure_ascii=False, indent=4)
    
    def scrape_chapter_content(self, novel_code, chapter_id):
        scraper = cloudscraper.create_scraper()
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-TW,zh;q=0.8,en-US;q=0.5,en;q=0.3',
            'Referer': 'https://czbooks.net/'
        }
        if chapter_id.startswith('//'):
            chapter_id = 'https:' + chapter_id
        response = scraper.get(chapter_id, headers=headers, timeout=10)
        soup = BeautifulSoup(response.content, 'html.parser')
        content_div = soup.find('div', class_='content')
        return content_div.text.strip() if content_div else None

class TtkanScraper:
    def __init__(self):
        self.base_url = 'https://www.ttkan.co/novel/chapters/'

    def load_chapters(self, novel_code):
        chapters_file = f'{novel_code}/chapters.json'
        if os.path.exists(chapters_file):
            with open(chapters_file, 'r', encoding='utf-8') as file:
                return json.load(file)
        return {}

    def scrape_chapters(self, novel_code):
        api_url = f'https://www.ttkan.co/api/nq/amp_novel_chapters?language=tw&novel_id={novel_code}'
        scraper = cloudscraper.create_scraper()
        response = scraper.get(api_url)
        if response.status_code != 200:
            messagebox.showerror('Error', f'Failed to load chapters: {response.status_code}')
            return {}
        chapters_data = response.json()
        chapters = {}
        for item in chapters_data.get('items', []):
            chapter_name = item['chapter_name']
            chapter_id = item['chapter_id']
            chapters[chapter_name] = chapter_id
        self.save_chapters(novel_code, chapters)
        return chapters

    def scrape_novel_title(self, novel_code):
        novel_url = f'{self.base_url}{novel_code}'
        scraper = cloudscraper.create_scraper()
        response = scraper.get(novel_url)
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            title_element = soup.select_one('div.novel_info h1')
            if title_element:
                return title_element.get_text(strip=True)
        return None

    def save_chapters(self, novel_code, chapters):
        os.makedirs(novel_code, exist_ok=True)
        chapters_file = f'{novel_code}/chapters.json'
        with open(chapters_file, 'w', encoding='utf-8') as file:
            json.dump(chapters, file, ensure_ascii=False, indent=4)

    def scrape_chapter_content(self, novel_code, chapter_id):
        chapter_url = f'https://www.wa01.com/novel/pagea/{novel_code}_{chapter_id}.html'
        scraper = cloudscraper.create_scraper()
        response = scraper.get(chapter_url)
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            content_div = soup.find('div', class_='content')
            if content_div:
                paragraphs = content_div.find_all('p')
                return '\n'.join(p.get_text(strip=True) for p in paragraphs)
        return None

class OtherScraper:
    def __init__(self):
        self.base_url = 'https://otherwebsite.com/n/'

    def load_chapters(self, novel_code):
        # 實作其他網站的章節載入邏輯
        pass

    def scrape_chapters(self, novel_code):
        # 實作其他網站的章節抓取邏輯
        pass

    def scrape_novel_title(self, novel_code):
        # 實作其他網站的小說名稱抓取邏輯
        pass

    def save_chapters(self, novel_code, chapters):
        # 實作其他網站的章節儲存邏輯
        pass
