import os

def detect_file_encoding(file_path: str, fallback: str = "utf-8") -> str:
    """
    智能检测文本文件的字符编码 (UTF-8, GBK, GB2312, UTF-16 等)
    """
    try:
        import chardet
        with open(file_path, 'rb') as f:
            raw_data = f.read(1024 * 30)
            if not raw_data:
                return fallback
            result = chardet.detect(raw_data)
            encoding = result.get('encoding')
            confidence = result.get('confidence', 0)
            
            if encoding and confidence > 0.5:
                enc_lower = encoding.lower()
                if enc_lower in ['gb2312', 'gbk', 'gb18030']:
                    return 'gb18030'
                if enc_lower in ['utf-8', 'utf-8-sig']:
                    return 'utf-8-sig' if raw_data.startswith(b'\xef\xbb\xbf') else 'utf-8'
                return encoding
    except ImportError:
        pass
    except Exception:
        pass
    
    # 尝试常用编码按顺序解码测试
    encodings_to_try = ['utf-8', 'gb18030', 'gbk', 'utf-16', 'big5', 'ansi']
    for enc in encodings_to_try:
        try:
            with open(file_path, 'r', encoding=enc) as f:
                f.read(1000)
            return enc
        except Exception:
            continue
            
    return fallback
