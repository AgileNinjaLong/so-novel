from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class Chapter:
    title: str
    content: str
    index: int = 0

    def __post_init__(self):
        self._cached_lines: Optional[List[str]] = None
        self._cached_line_length: int = 0

    def get_lines(self, line_length: int = 40) -> List[str]:
        """将章节内容高效拆分为适应摸鱼窄条/控制台的微型行，带缓存优化"""
        if self._cached_lines is not None and self._cached_line_length == line_length:
            return self._cached_lines

        formatted_lines = []
        raw_lines = self.content.splitlines()
        for line in raw_lines:
            line_str = line.strip()
            if not line_str:
                continue
            # 高效切片取代字符串复制循环
            for i in range(0, len(line_str), line_length):
                formatted_lines.append(line_str[i:i + line_length])
                
        self._cached_lines = formatted_lines if formatted_lines else [self.title]
        self._cached_line_length = line_length
        return self._cached_lines

@dataclass
class Book:
    title: str
    file_path: str
    format: str  # 'txt', 'epub', 'pdf', 'mobi'
    author: str = "Unknown"
    chapters: List[Chapter] = field(default_factory=list)
    current_chapter_idx: int = 0
    current_line_idx: int = 0

    @property
    def total_chapters(self) -> int:
        return len(self.chapters)

    def get_current_chapter(self) -> Optional[Chapter]:
        if 0 <= self.current_chapter_idx < len(self.chapters):
            return self.chapters[self.current_chapter_idx]
        return None

    def next_chapter(self) -> bool:
        if self.current_chapter_idx < len(self.chapters) - 1:
            self.current_chapter_idx += 1
            self.current_line_idx = 0
            return True
        return False

    def prev_chapter(self) -> bool:
        if self.current_chapter_idx > 0:
            self.current_chapter_idx -= 1
            self.current_line_idx = 0
            return True
        return False
