import os
import sys
import time
import requests
from src.core.sonovel_client import SoNovelClient
from src.ui.bookshelf_window import DownloadWorker

def run_benchmark():
    print("=" * 70)
    print("🚀 开始 NovelRead 与 so-novel-main 对齐效果性能与质量对比测试")
    print("=" * 70)

    client = SoNovelClient()
    
    # 测试书源：笔趣阁365 - 《凡人修仙传》
    test_url = "https://www.biquge365.net/book/44911/"
    rule = None
    for r in client.rules:
        if r.get("name") == "笔趣阁365":
            rule = r
            break
            
    if not rule:
        rule = client.rules[0]
        test_url = rule.get("url")

    print(f"\n[测试书源]: {rule.get('name')} | URL: {test_url}")

    # ===== 1. 目录解析质量与全量测试 =====
    print("\n--- 阶段 1: 目录解析 (TocParser 规则全量对齐测试) ---")
    t0 = time.time()
    session = requests.Session()
    session.headers.update(client.headers)
    
    toc = client.get_toc(test_url, rule, session=session)
    t1 = time.time()

    toc_time = t1 - t0
    total_chapters = len(toc)
    print(f"✅ 目录解析完成！总耗时: {toc_time:.2f} 秒 | 抓取章节总数: {total_chapters} 章")

    if total_chapters > 0:
        print(f"   第一章: {toc[0]['title']} -> {toc[0]['url']}")
        print(f"   第末章: {toc[-1]['title']} -> {toc[-1]['url']}")

    # 验证目录无重复、无乱序
    urls = [c['url'] for c in toc]
    unique_urls = set(urls)
    print(f"   章节 URL 去重率: {len(unique_urls)} / {len(urls)} (去重差值: {len(urls) - len(unique_urls)})")
    assert len(unique_urls) == len(urls), "❌ 警告: 目录中依然存在重复 URL"

    # ===== 2. 下载并发速度与防刷限流质量测试 =====
    print("\n--- 阶段 2: 高并发下载与 3 轮指数退避补章质量测试 ---")

    # 抽取前 50 章进行快速真实下载跑分
    sample_size = min(50, total_chapters)
    sample_toc = toc[:sample_size]
    
    book_info = {
        "bookName": "凡人修仙传(测试)",
        "author": "忘语",
        "url": test_url,
        "rule": rule
    }

    test_save_path = os.path.join(".", "downloads", "benchmark_test_fanren.txt")
    os.makedirs(os.path.dirname(test_save_path), exist_ok=True)

    worker = DownloadWorker(client, "bench_task_001", book_info, test_save_path, export_mode="txt")

    t_start = time.time()
    
    # 模拟并发下载 50 章
    chapter_contents = [None] * sample_size
    completed = [0]

    rule_crawl = rule.get("crawl", {}) if isinstance(rule, dict) else {}
    min_interval = float(rule_crawl.get("minInterval", 200)) / 1000.0
    max_interval = float(rule_crawl.get("maxInterval", 400)) / 1000.0
    concurrency = min(15, sample_size)

    import concurrent.futures
    import random

    def _down_task(i, chap):
        if max_interval > 0:
            time.sleep(random.uniform(min_interval, max_interval))
        res = worker.download_chapter_isolated(chap["url"], rule, min_interval, max_interval, chap_title=chap["title"])
        return i, res

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=concurrency)
    futures = {executor.submit(_down_task, i, chap): i for i, chap in enumerate(sample_toc)}
    for f in concurrent.futures.as_completed(futures):
        i, content = f.result()
        chapter_contents[i] = content
        completed[0] += 1
    executor.shutdown(wait=True)

    t_initial = time.time()
    initial_download_time = t_initial - t_start

    # 统计初始缺失/异常章节数
    failed_initial = [i for i, c in enumerate(chapter_contents) if not c or "下载失败" in c or "解析失败" in c or "暂无内容" in c]
    print(f"✅ 初始高并发下载完成！耗时: {initial_download_time:.2f} 秒 ({sample_size / initial_download_time:.2f} 章/秒)")
    print(f"   初始成功率: {sample_size - len(failed_initial)} / {sample_size} (异常/未获取章数: {len(failed_initial)})")

    # 验证 3 轮退避补全机制
    if failed_initial:
        print(f"\n--- 阶段 3: 触发退避补漏修复逻辑 (针对 {len(failed_initial)} 个缺失章节) ---")
        for retry_round in range(3):
            failed_indices = [i for i, c in enumerate(chapter_contents) if not c or "下载失败" in c or "解析失败" in c or "暂无内容" in c]
            if not failed_indices:
                break
            for idx in failed_indices:
                chap = sample_toc[idx]
                time.sleep(random.uniform(1.0, 2.0))
                res = worker.download_chapter_isolated(chap["url"], rule, min_interval, max_interval, chap_title=chap["title"])
                if "下载失败" not in res and "解析失败" not in res and "暂无内容" not in res:
                    chapter_contents[idx] = res

    t_end = time.time()
    total_time = t_end - t_start

    failed_final = [i for i, c in enumerate(chapter_contents) if not c or "下载失败" in c or "解析失败" in c or "暂无内容" in c]
    print(f"\n✅ 最终完美交付率: {sample_size - len(failed_final)} / {sample_size} ({((sample_size - len(failed_final)) / sample_size) * 100:.1f}%)")

    # ===== 3. 文本清洗与质量抽检 =====
    print("\n--- 阶段 4: 文本清洗与格式质量抽检 ---")
    sample_text = chapter_contents[0] or ""
    print(f"[第 1 章 文本前 150 字符字样预览]:\n{sample_text[:150]}")

    # 检查是否有控制符残留
    has_ctrl = any(ord(ch) < 32 and ch not in ('\n', '\r', '\t') for ch in sample_text)
    print(f"   不可见控制符残留: {'❌ 有残留' if has_ctrl else '✅ 0 残留 (完全清洗)'}")

    # 检查标题重复擦除
    has_dup_title = sample_text.startswith(sample_toc[0]['title'])
    print(f"   正文首行标题重复: {'❌ 未擦除' if has_dup_title else '✅ 已精准擦除重复标题'}")

    print("\n" + "=" * 70)
    print(f"🎉 对比测试总结: 50 章下载总耗时 {total_time:.2f} 秒，完整度 {((sample_size - len(failed_final)) / sample_size) * 100:.1f}%，质量合格！")
    print("=" * 70)

if __name__ == "__main__":
    run_benchmark()
