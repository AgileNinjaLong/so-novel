import os
import time
import requests
from src.core.sonovel_client import SoNovelClient
from src.ui.bookshelf_window import DownloadWorker

def test_dongtan():
    client = SoNovelClient()
    rule = None
    for r in client.rules:
        if r.get("name") == "东滩小说":
            rule = r
            break
            
    print(f"找到规则: {rule.get('name')} | Rule Origin File: {rule.get('rule_file', 'cloudflare.json')}")

    # 搜索 《吞噬星空》
    search_res = client._search_single_rule(rule, "吞噬星空")
    if not search_res:
        print("搜索 《吞噬星空》 未找到结果！")
        return

    book_item = search_res[0]
    print(f"找到图书: 《{book_item['bookName']}》 | URL: {book_item['url']}")

    # 解析目录
    session = requests.Session()
    session.headers.update(client.headers)
    toc = client.get_toc(book_item['url'], rule, session=session)
    print(f"目录解析完成，包含 {len(toc)} 章。")

    # 模拟限制线程数为 5，间距 0.5s
    sample_size = 30
    sample_toc = toc[:sample_size]
    
    worker = DownloadWorker(client, "test_dongtan", book_item, "./downloads/dongtan_test.txt", export_mode="txt")

    print("\n--- 开始使用防刷并发 (5 线程, 0.5s ~ 1.0s 随机延时) 下载前 30 章 ---")
    t0 = time.time()
    
    chapter_contents = [None] * sample_size
    import concurrent.futures
    import random

    def _down(i, chap):
        time.sleep(random.uniform(0.5, 1.0))
        res = worker.download_chapter_isolated(chap["url"], rule, 0.5, 1.0, chap_title=chap["title"])
        return i, res

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=5)
    futures = {executor.submit(_down, i, chap): i for i, chap in enumerate(sample_toc)}
    for f in concurrent.futures.as_completed(futures):
        i, content = f.result()
        chapter_contents[i] = content
    executor.shutdown(wait=True)

    t1 = time.time()

    failed = [i for i, c in enumerate(chapter_contents) if not c or "下载失败" in c or "解析失败" in c or "暂无内容" in c]
    print(f"✅ 下载完成！耗时: {t1-t0:.2f} 秒 | 成功: {sample_size - len(failed)} / {sample_size} (失败/缺失: {len(failed)})")
    if chapter_contents[0]:
        print(f"\n[第 1 章 内容预览]:\n{chapter_contents[0][:120]}...")

if __name__ == "__main__":
    test_dongtan()
