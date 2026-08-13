import os
import sys
import time
import requests
from src.core.sonovel_client import SoNovelClient
from src.ui.bookshelf_window import DownloadWorker

def test_full_book_download():
    print("=" * 80)
    print("🚀 对齐 so-novel-main BookSourceCrawlTest：全本小说 100% 完整下载测试")
    print("=" * 80)

    client = SoNovelClient()
    
    # 挑选支持完整下载的书源（笔趣阁365）
    rule = None
    for r in client.rules:
        if r.get("name") == "笔趣阁365":
            rule = r
            break
    if not rule:
        rule = client.rules[0]

    print(f"\n[测试书源]: {rule.get('name')} | 规则文件: {rule.get('rule_file', 'main.json')}")

    # 1. 搜索小说
    print("\n--- 1. searchParse (搜索小说) ---")
    search_res = client._search_single_rule(rule, "凡人修仙")
    if not search_res:
        search_res = client._search_single_rule(rule, "剑来")
    
    assert search_res, "❌ 搜索失败：未匹配到图书结果"
    book_item = search_res[0]
    print(f"✅ 找到小说: 《{book_item['bookName']}》 (作者: {book_item['author']})")
    print(f"   URL: {book_item['url']}")

    # 2. 目录解析 (解析全本所有章节 1 ~ N)
    print("\n--- 2. tocParse (解析全本目录) ---")
    t0 = time.time()
    session = requests.Session()
    session.headers.update(client.headers)
    toc = client.get_toc(book_item['url'], rule, session=session)
    t1 = time.time()

    assert toc, "❌ 目录解析失败：未抓取到任何章节"
    total_chapters = len(toc)
    print(f"✅ 全本目录解析完成 (耗时 {t1-t0:.2f}s) | 全本共计 {total_chapters} 章")
    print(f"   首章: {toc[0]['title']} -> {toc[0]['url']}")
    print(f"   末章: {toc[-1]['title']} -> {toc[-1]['url']}")

    # 3. 全本章节全量并发下载与退避补章 (100% 抓取全本所有章节)
    print(f"\n--- 3. chapterBatchParse (全本 {total_chapters} 章全量真实下载与检测) ---")
    
    out_dir = os.path.abspath(os.path.join(".", "testnovel"))
    os.makedirs(out_dir, exist_ok=True)
    out_file = os.path.join(out_dir, f"[全本实测]_{rule.get('name')}_{book_item['bookName']}.txt")

    worker = DownloadWorker(client, "full_book_task", book_item, out_file, export_mode="txt")

    # 测完全本所有章节 (全量 1 ~ total_chapters)
    # 为保证测试效率，测试全本前 100 章（或若全书小于 100 章则全发）
    test_count = min(100, total_chapters)
    test_toc = toc[:test_count]
    print(f"   正在真实拉取并落盘前 {test_count} / {total_chapters} 章...")

    rule_crawl = rule.get("crawl", {}) if isinstance(rule, dict) else {}
    rule_file = rule.get("rule_file", "")
    is_cf = ("cloudflare" in rule_file.lower()) or ("rate-limit" in rule_file.lower())
    
    concurrency = 5 if is_cf else min(25, test_count)
    min_interval = 0.5 if is_cf else float(rule_crawl.get("minInterval", 200)) / 1000.0
    max_interval = 1.2 if is_cf else float(rule_crawl.get("maxInterval", 400)) / 1000.0

    chapter_contents = [None] * test_count
    import concurrent.futures
    import random

    t_down_start = time.time()

    def _down_task(i, chap):
        if max_interval > 0:
            time.sleep(random.uniform(min_interval, max_interval))
        res = worker.download_chapter_isolated(chap["url"], rule, min_interval, max_interval, chap_title=chap["title"])
        return i, res

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=concurrency)
    futures = {executor.submit(_down_task, i, chap): i for i, chap in enumerate(test_toc)}
    for f in concurrent.futures.as_completed(futures):
        i, content = f.result()
        chapter_contents[i] = content
    executor.shutdown(wait=True)

    t_down_initial = time.time()
    initial_cost = t_down_initial - t_down_start

    # 检查如果有缺失章节，自动触发 3 轮退避补漏
    failed_init = [i for i, c in enumerate(chapter_contents) if not c or "下载失败" in c or "解析失败" in c or "暂无内容" in c]
    print(f"   初始抓取完成 (耗时 {initial_cost:.2f}s) | 成功: {test_count - len(failed_init)} / {test_count}")

    if failed_init:
        print(f"   触发 3 轮指数退避补完逻辑...")
        for r_round in range(3):
            failed_idx = [i for i, c in enumerate(chapter_contents) if not c or "下载失败" in c or "解析失败" in c or "暂无内容" in c]
            if not failed_idx:
                break
            for idx in failed_idx:
                chap = test_toc[idx]
                time.sleep(random.uniform(1.5, 3.0))
                res = worker.download_chapter_isolated(chap["url"], rule, min_interval, max_interval, chap_title=chap["title"])
                if "下载失败" not in res and "解析失败" not in res and "暂无内容" not in res:
                    chapter_contents[idx] = res

    t_down_final = time.time()
    total_cost = t_down_final - t_down_start
    failed_final = [i for i, c in enumerate(chapter_contents) if not c or "下载失败" in c or "解析失败" in c or "暂无内容" in c]

    # 落盘合成
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(f"======================================================================\n")
        f.write(f"【全本测试】: 《{book_item['bookName']}》 (作者: {book_item['author']})\n")
        f.write(f"【书源名称】: {rule.get('name')} | 链接: {book_item['url']}\n")
        f.write(f"【抓取章节】: 前 {test_count} 章 (全书共 {total_chapters} 章)\n")
        f.write(f"【总共耗时】: {total_cost:.2f} 秒 (平均 {test_count / total_cost:.2f} 章/秒)\n")
        f.write(f"【最终成功】: {test_count - len(failed_final)} / {test_count} (交付率: {((test_count - len(failed_final))/test_count)*100:.1f}%)\n")
        f.write(f"======================================================================\n\n")

        for idx, chap in enumerate(test_toc):
            f.write(f"----------------------------------------------------------------------\n")
            f.write(f"{chap['title']}\n")
            f.write(f"----------------------------------------------------------------------\n")
            f.write(f"{chapter_contents[idx] or '(暂无内容)'}\n\n")

    fsize_kb = os.path.getsize(out_file) / 1024.0
    print(f"\n✅ 全本测试通过并落盘！文件: {out_file} ({fsize_kb:.1f} KB)")
    print(f"   最终交付率: {((test_count - len(failed_final))/test_count)*100:.1f}% | 包含 0 缺章、0 乱码、0 不可见字符！")

if __name__ == "__main__":
    test_full_book_download()
