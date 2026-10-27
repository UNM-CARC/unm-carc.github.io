import json
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from news_ticker import ticker_html, downtime_entries


class TickerTests(unittest.TestCase):
    def test_links_and_anchors_resolve(self):
        for notice in downtime_entries(ROOT / 'docs'):
            anchor = notice['url'].split('#')[1]
            self.assertIn(f'id="{anchor}"', (ROOT / 'docs/downtime-notices.md').read_text())
        markup = ticker_html(ROOT / 'docs')
        data = json.loads(re.search(r'id="gg-ticker-data">(.*?)</script>', markup)[1])
        self.assertGreater(len(data['news']), 0)
        self.assertEqual([item['date'] for item in data['news']],
                         sorted((item['date'] for item in data['news']), reverse=True))
        for entry in data['news']:
            self.assertTrue((ROOT / 'docs' / (entry['url'].rstrip('/') + '.md')).is_file())
        self.assertLessEqual(len(data['news']), 6)
