import sys
import time
import os
from src.core.sonovel_client import SoNovelClient

print('Initializing SoNovelClient...')
client = SoNovelClient()

keyword = '我在精神病院学斩神'
print(f'Searching for: {keyword} ...')
t0 = time.time()
results = client.search(keyword)
t1 = time.time()

print(f'Search finished in {t1 - t0:.2f} seconds. Total results: {len(results)}')

if not results:
    print('Failed to find any results!')
    sys.exit(1)

print('\nTop 5 Results:')
for i, r in enumerate(results[:5]):
    print(f"{i+1}. Book: {r['bookName']}, Author: {r['author']}, Source: {r['sourceName']}")

# Download test
book = results[0]
print(f'\nFetching TOC for [{book["bookName"]}] from [{book["sourceName"]}]...')
toc = client.get_toc(book['url'], book['rule'])
print(f'TOC fetched: {len(toc)} chapters.')

if not toc:
    print('Failed to fetch TOC!')
    sys.exit(1)

print(f'\nDownloading first chapter: {toc[0]["title"]} at URL: {toc[0]["url"]} ...')
content = client.download_chapter(toc[0]['url'], book['rule'])
print(f'Content length: {len(content)} characters.')
print(f'Preview:\n{content[:200]}...')
