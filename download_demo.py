import os
from src.core.sonovel_client import SoNovelClient

client = SoNovelClient()
results = client.search('我在精神病院学斩神')
book = [r for r in results if r['sourceName'] == '笔趣阁365'][0]
toc = client.get_toc(book['url'], book['rule'])

save_dir = r'D:\documents\novelRead\dist\download'
os.makedirs(save_dir, exist_ok=True)
save_path = os.path.join(save_dir, '我在精神病院学斩神_三九音域.txt')

print(f"Downloading and saving to {save_path} ...")

with open(save_path, 'w', encoding='utf-8') as f:
    for i, chap in enumerate(toc[:50]): # Only 50 chapters to be fast
        try:
            content = client.download_chapter(chap['url'], book['rule'])
            f.write(f"\n\n{chap['title']}\n\n{content}\n")
            print(f"Downloaded: {chap['title']}")
        except Exception as e:
            print(f"Error on {chap['title']}: {e}")

print("Done! First 50 chapters saved.")
