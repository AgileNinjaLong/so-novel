import time
from src.core.sonovel_client import SoNovelClient

client = SoNovelClient()
print("Searching for test novel...")
t0 = time.time()
res = client.search('凡人修仙', search_type='title')
t1 = time.time()

print(f"Search completed in {t1 - t0:.2f} seconds. Total results: {len(res)}")
for i, r in enumerate(res[:5]):
    print(f"[{i+1}] {r.get('bookName')} | 作者: {r.get('author')} | 书源: {r.get('sourceName')} | URL: {r.get('url')}")
