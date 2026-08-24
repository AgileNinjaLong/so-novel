import os
import sys
import time
import re
from PyQt6.QtCore import QCoreApplication

from src.core.sonovel_client import SoNovelClient
from src.ui.bookshelf_window import DownloadWorker

def run_tests():
    app = QCoreApplication(sys.argv)
    client = SoNovelClient()
    
    test_dir = os.path.join(os.path.abspath("."), "testnovel")
    os.makedirs(test_dir, exist_ok=True)
    
    report_path = os.path.join(test_dir, "TEST_REPORT.md")
    
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# 24 书源真实下载实测报告与速度基准\n\n")
        f.write("> 测试规范：至少下载 200 章，下载时长必须在 2 分钟以内。\n\n")
        f.write("| 序号 | 书源名称 | 测试小说 | 下载章数 | 耗时(秒) | 平均速度(章/秒) | 状态 | 产物文件 |\n")
        f.write("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n")

    keywords = ["凡人修仙传", "斗破苍穹", "剑来", "诡秘之主", "遮天", "一念永恒", "仙逆", "完美世界"]
    
    print(f"============================================================")
    print(f"🚀 开始对全量 {len(client.rules)} 个书源进行小说下载实测")
    print(f"============================================================")
    
    for idx, rule in enumerate(client.rules, 1):
        r_name = rule.get("name", f"书源_{idx}")
        print(f"\n[{idx}/{len(client.rules)}] 正在测试书源: 【{r_name}】...")
        
        # 1. 连通性测试
        is_ok, lat = client.test_rule_connectivity(rule)
        if not is_ok:
            print(f"  ❌ 连通性失败 (可能域名失效/反爬拦截)")
            with open(report_path, "a", encoding="utf-8") as f:
                f.write(f"| {idx} | {r_name} | - | - | - | - | ❌ 连通失败 | - |\n")
            continue
            
        print(f"  ✅ 连通正常 (延迟: {lat}ms)，开始多词搜书...")
        
        # 2. 尝试多种关键词搜书
        book_info = None
        for kw in keywords:
            try:
                res = client._search_single_rule(rule, kw)
                if res and len(res) > 0:
                    book_info = res[0]
                    break
            except Exception:
                pass
                
        if not book_info:
            print(f"  ⚠️ 搜索无可用结果")
            with open(report_path, "a", encoding="utf-8") as f:
                f.write(f"| {idx} | {r_name} | - | - | - | - | ⚠️ 搜索无结果 | - |\n")
            continue
            
        b_name = book_info.get("bookName", "未知书名")
        url = book_info.get("url", "")
        print(f"  📖 找到小说: 《{b_name}》 链接: {url}")
        
        # 3. 获取目录
        try:
            toc = client.get_toc(url, rule)
        except Exception as e:
            print(f"  ❌ 目录获取异常: {e}")
            with open(report_path, "a", encoding="utf-8") as f:
                f.write(f"| {idx} | {r_name} | {b_name} | 0 | - | - | ❌ 目录解析失败 | - |\n")
            continue
            
        print(f"  📑 目录获取成功，共包含 {len(toc)} 章")
        
        if len(toc) < 200:
            print(f"  ⚠️ 章数不足 200 章 (仅 {len(toc)} 章)，跳过")
            with open(report_path, "a", encoding="utf-8") as f:
                f.write(f"| {idx} | {r_name} | {b_name} | {len(toc)} | - | - | ⚠️ 章数不足200章 | - |\n")
            continue
            
        # 截取前 200~300 章进行标准基准测试 (至少200章)
        target_count = min(len(toc), 250)
        target_toc = toc[:target_count]
        
        # 覆写 client.get_toc 使 DownloadWorker 严格下载目标章节
        original_get_toc = client.get_toc
        client.get_toc = lambda *args, **kwargs: target_toc
        
        safe_title = re.sub(r'[\\/:*?"<>|]', '_', b_name)
        safe_source = re.sub(r'[\\/:*?"<>|]', '_', r_name)
        file_name = f"[{safe_source}]_{safe_title}.txt"
        save_path = os.path.join(test_dir, file_name)
        
        print(f"  ⬇️ 启动 DownloadWorker 线程下载 {target_count} 章...")
        worker = DownloadWorker(client, f"task_{idx}", book_info, save_path, "txt")
        
        t0 = time.time()
        is_finished = False
        final_msg = ""
        
        def on_finished(tid, path):
            nonlocal is_finished, final_msg
            is_finished = True
            final_msg = "成功"
            
        def on_error(tid, msg):
            nonlocal is_finished, final_msg
            is_finished = True
            final_msg = f"失败: {msg}"
            
        def on_progress(tid, cur, total, msg):
            if cur > 0 and (cur % 50 == 0 or cur == total):
                print(f"    -> 进度: {cur}/{total} 章...")
            
        worker.finished_signal.connect(on_finished)
        worker.error_signal.connect(on_error)
        worker.progress_signal.connect(on_progress)
        
        worker.start()
        
        while not is_finished:
            app.processEvents()
            time.sleep(0.05)
            if time.time() - t0 > 120: # 严格限制2分钟超时
                worker.cancel()
                final_msg = "超时 (>120s)"
                break
                
        elapsed = time.time() - t0
        client.get_toc = original_get_toc
        
        speed = target_count / elapsed if elapsed > 0 else 0
        
        # 验证文件落盘与大小
        file_size_kb = 0
        if os.path.exists(save_path):
            file_size_kb = os.path.getsize(save_path) / 1024.0
            
        if final_msg == "成功" and file_size_kb > 50:
            status_str = "✅ 成功"
            print(f"  🎉 下载成功！耗时: {elapsed:.2f}s, 平均速度: {speed:.1f}章/秒, 大小: {file_size_kb:.1f} KB")
        else:
            status_str = f"❌ {final_msg}"
            print(f"  ❌ 下载异常或未完成: {final_msg}, 大小: {file_size_kb:.1f} KB")
            
        with open(report_path, "a", encoding="utf-8") as f:
            f.write(f"| {idx} | {r_name} | 《{b_name}》 | {target_count} | {elapsed:.2f} | {speed:.1f} | {status_str} | `{file_name}` ({file_size_kb:.1f}KB) |\n")

    print(f"\n============================================================")
    print(f"🏁 全量书源下载测试完毕！报告已生成在: {report_path}")
    print(f"============================================================")

if __name__ == "__main__":
    run_tests()
