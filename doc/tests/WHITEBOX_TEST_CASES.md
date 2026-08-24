# WHITEBOX_TEST_CASES.md

This document outlines specific white-box test cases to support the modularization and upcoming features: per-mode styling configurations and dynamic font-size-based text reflow.

---

## 1. Architectural Analysis of Tight Coupling (UI vs. Core Logic)

### A. Window Dragging and Edge Resizing Coupling
* **Implementation Detail**: Because `BaseStealthWindow` uses frameless flags (`Qt.WindowType.FramelessWindowHint`), the standard OS title bar and borders are absent. Custom window boundary detection and coordinate math are coded in `BaseStealthWindow` via `mousePressEvent`, `mouseMoveEvent`, `mouseReleaseEvent`, and `get_resize_edge`.
* **Coupling Issue**: Since stealth views contain nested widgets (e.g. `QTextEdit` in IDE view, `QTableWidget` in Excel/Stock views) that swallow mouse events, the project introduced event-forwarding sub-widgets. These subclasses manually map and forward mouse events back to the parent `BaseStealthWindow`.
* **Impact**: Window management logic is tightly bound to specific subclassing of child widgets. Testing window resize/drag requires simulated widget mouse events and a fully running GUI display server.

### B. File Slicing, Progress Tracking, and Navigation Coupling
* **Implementation Detail**: `BaseStealthWindow` manages book loading and progress tracking database calls. It also handles navigation control and slicing pagination (`recalculate_lines`).
* **Coupling Issue**: Pagination is mixed with the widget state. Slicing logic varies: `FloatingView` overrides `recalculate_lines` to perform pixel-based pagination using `QTextLayout` and the active widget font, whereas other views use simple character-length splitting. 
* **Impact**: Reading sessions, line-boundary checking, auto-scroll progress transitions, and pagination cannot be unit-tested headlessly.

---

## 2. White-Box Test Cases for Upcoming Features

### Feature A: Per-Mode Font Color/Size Configurations

#### Background & Target Architecture
Currently, styling is hardcoded inside individual view widgets using string-based QSS. We plan to refactor `ConfigManager` to support a nested configuration dictionary (`mode_styles`) in `config.json` that looks like:
```json
"mode_styles": {
    "excel_sheet": {
        "font_size": 11,
        "font_color": "#9CDCFE",
        "bg_color": "#1E1E1E"
    },
    "floating": {
        "font_size": 11,
        "font_color": "#333333",
        "bg_color": "#FFFFFF"
    }
}
```
If a mode-specific property is missing, the system falls back to the global default configuration values.

#### Test Case A.1: Configuration Style Resolution & Fallback Verification
* **Test Object**: `ConfigManager`
* **Test Objective**: Verify that requesting style properties for a mode retrieves the specific configuration if defined, and successfully falls back to global default styles if absent.
* **Preconditions**: `ConfigManager` initialized with a temporary JSON config containing global defaults and mode overrides.
* **Expected Assertions**: `excel_sheet` font size resolves to override, `ide_pseudo` falls back to global default.

#### Test Case A.2: Configuration Change Isolation
* **Test Object**: `ConfigManager`
* **Test Objective**: Ensure that editing styling settings for one mode does not impact or overwrite settings of other modes or the global settings.
* **Expected Assertions**: Changing one mode updates only that mode's dictionary entry and correctly persists to `config.json`.

---

### Feature B: Dynamic Text Layout/Reflow Calculation Based on Font Size

#### Test Case B.1: Word Wrap Reflow Slicing for ASCII/English
* **Test Code Location**: `tests/test_layout_engine.py` (new file)
* **Test Objective**: Ensure English paragraphs are wrapped cleanly on word-spaces rather than splitting words in half, based on the target container width.

#### Test Case B.2: CJK / Chinese Character Slicing Width Accuracy
* **Test Object**: Layout reflow logic.
* **Test Objective**: Ensure Chinese text slices accurately at pixel boundaries matching character counts, preventing overlap and clipping when window resizes.

#### Test Case B.3: Layout Reflow and Current Line Index Mapping
* **Test Objective**: Ensure that when container width changes (window resize) or font size changes, the reflow mapper adjusts the `current_line_idx` so that the reader remains at the same position in the story.
