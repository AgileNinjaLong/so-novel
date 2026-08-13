import os
import sys
import time
import requests
from src.core.sonovel_client import SoNovelClient
from src.ui.bookshelf_window import DownloadWorker

TEST_DIR = os.path.abspath(os.path.join(".", "testnovel"))

def run_all_sources_test():
    print("=" * 80)
    print("🚀 开始全量书源连通性测试并真实落盘到 testnovel/ 文件夹")
    print("=" * 80)

    os.makedirs(TEST_DIR, exist_ok=True)
    print(f"输出落盘目标目录: {TEST_DIR}\n")

    client = SoNovelClient()
    total_rules = len(client.rules)
    print(f"载入规则库: 共计 {total_rules} 个书源规则\n")

    valid_rules = []
    print("--- 1. 并发测试所有 25 个书源连通性 ---")
    for idx, rule in enumerate(client.rules):
        r_name = rule.get("name", "未知书源")
        r_idx = rule.get("rule_index", idx)
        is_ok, latency = client.test_rule_connectivity(rule)
        if is_ok:
            print(f"  [#{r_idx+1:02d}] ✅ 连通成功: {r_name:<16} (延迟: {latency} ms)")
            valid_rules.append(rule)
        else:
            print(f"  [#{r_idx+1:02d}] ❌ 无法连通: {r_name:<16}")

    print(f"\n连通性测试完成！共有 {len(valid_rules)} / {total_rules} 个书源可用。\n")

    print("=" * 80)
    print("--- 2. 对所有连通成功的书源进行真实搜书与章节下载落盘 ---")
    print("=" * 80)

    keywords = ["凡人修仙", "剑来", "完美世界", "诡秘之主", "元尊", "斗罗大陆", "修仙", "万古"]
    success_downloads = []

    for idx, rule in enumerate(valid_rules):
        r_name = rule.get("name", "未知书源")
        print(f"\n[{idx+1}/{len(valid_rules)}] 正在测试书源: 【{r_name}】")
        
        search_res = []
        for kw in keywords:
            search_res = client._search_single_rule(rule, kw)
            if search_res:
                break
            time.sleep(0.3)
            
        if not search_res:
            print(f"  ⚠️  【{r_name}】搜索未匹配到样本小说，跳过下载。")
            continue

        book_item = search_res[0]
        b_title = book_item.get("bookName", "未知小说")
        a_name = book_item.get("author", "未知作者")
        b_url = book_item.get("url", "")

        print(f"  📖 找到样本图书: 《{b_title}》 (作者: {a_name})")
        print(f"  🔗 目标 URL: {b_url}")

        # 抓取目录
        t0 = time.time()
        session = requests.Session()
        session.headers.update(client.headers)
        toc = client.get_toc(b_url, rule, session=session)
        t1 = time.time()

        if not toc:
            print(f"  ❌ 【{r_name}】解析目录失败或受到站点防护阻拦，跳过该书源。")
            continue

        print(f"  ✅ 目录解析成功 ({t1-t0:.2f}s)，包含 {len(toc)} 章。第一章: {toc[0]['title']}")

        # 抽取前 20 章进行真实落盘写文件
        sample_size = min(20, len(toc))
        sample_toc = toc[:sample_size]

        safe_r_name = r_name.replace("/", "_").replace("\\", "_")
        safe_b_title = b_title.replace("/", "_").replace("\\", "_")
        safe_a_name = a_name.replace("/", "_").replace("\\", "_")

        out_file_name = f"[{safe_r_name}]_{safe_b_title}_({safe_a_name}).txt"
        out_file_path = os.path.join(TEST_DIR, out_file_name)

        worker = DownloadWorker(client, f"test_{idx}", book_item, out_file_path, export_mode="txt")

        # 线程池抓取
        chapter_contents = [None] * sample_size
        rule_crawl = rule.get("crawl", {}) if isinstance(rule, dict) else {}
        min_interval = float(rule_crawl.get("minInterval", 200)) / 1000.0
        max_interval = float(rule_crawl.get("maxInterval", 400)) / 1000.0

        import concurrent.futures
        import random

        def _down(i, chap):
            if max_interval > 0:
                time.sleep(random.uniform(min_interval, max_interval))
            res = worker.download_chapter_isolated(chap["url"], rule, min_interval, max_interval, chap_title=chap["title"])
            return i, res

        t_down_0 = time.time()
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=min(10, sample_size))
        futures = {executor.submit(_down, i, chap): i for i, chap in enumerate(sample_toc)}
        for f in concurrent.futures.as_completed(futures):
            i, content = f.result()
            chapter_contents[i] = content
        executor.shutdown(wait=True)
        t_down_1 = time.time()

        # 真实落盘写入 testnovel/ 文件夹
        with open(out_file_path, "w", encoding="utf-8") as f:
            f.write(f"======================================================================\n")
            f.write(f"【书源名称】: {r_name}\n")
            f.write(f"【小说名称】: {b_title}\n")
            f.write(f"【作者名称】: {a_name}\n")
            f.write(f"【图书链接】: {b_url}\n")
            f.write(f"【下载时间】: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"【目录总数】: {len(toc)} 章 (本次真实落盘前 {sample_size} 章，耗时 {t_down_1 - t_down_0:.2f}s)\n")
            f.write(f"======================================================================\n\n")

            for i, chap in enumerate(sample_toc):
                f.write(f"----------------------------------------------------------------------\n")
                f.write(f"{chap['title']}\n")
                f.write(f"----------------------------------------------------------------------\n")
                f.write(f"{chapter_contents[i] or '(暂无内容)'}\n\n")

        file_size_kb = os.path.getsize(out_file_path) / 1024.0
        print(f"  🎉 真实落盘保存成功! 路径: testnovel/{out_file_name} (文件大小: {file_size_kb:.1f} KB)")
        success_downloads.append((r_name, b_title, a_name, out_file_path, file_size_kb))

    print("\n" + "=" * 80)
    print("📊 最终总结：所有可用书源真实落盘完成报告")
    print("=" * 80)
    print(f"成功落盘文件总数: {len(success_downloads)} 本，位于目录: {TEST_DIR}\n")
    for r_name, b_title, a_name, path, fsize in success_downloads:
        fname = os.path.basename(path)
        print(f"  • {fname:<60} ({fsize:.1f} KB)")

if __name__ == "__main__":
    run_all_sources_test()
