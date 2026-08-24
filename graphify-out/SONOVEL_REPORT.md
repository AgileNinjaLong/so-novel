# Graph Report - so-novel-main  (2026-08-13)

## Corpus Check
- 134 files · ~117,384 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 484 nodes · 1457 edges · 33 communities (21 shown, 12 thin omitted)
- Extraction: 82% EXTRACTED · 18% INFERRED · 0% AMBIGUOUS · INFERRED: 260 edges (avg confidence: 0.8)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 20|Community 20]]
- [[_COMMUNITY_Community 21|Community 21]]
- [[_COMMUNITY_Community 22|Community 22]]
- [[_COMMUNITY_Community 23|Community 23]]
- [[_COMMUNITY_Community 24|Community 24]]
- [[_COMMUNITY_Community 32|Community 32]]

## God Nodes (most connected - your core abstractions)
1. `AppConfig` - 44 edges
2. `Book` - 38 edges
3. `SearchResult` - 25 edges
4. `Source` - 20 edges
5. `Rule` - 16 edges
6. `SearchParser` - 12 edges
7. `ChapterParser` - 11 edges
8. `TocParser` - 11 edges
9. `LogUtils` - 11 edges
10. `SourceUtils` - 11 edges

## Surprising Connections (you probably didn't know these)
- `ChapterFilter` --inherits--> `Source`  [EXTRACTED]
  src/main/java/com/pcdd/sonovel/core/ChapterFilter.java → src/main/java/com/pcdd/sonovel/core/Source.java
- `BookParser` --inherits--> `Source`  [EXTRACTED]
  src/main/java/com/pcdd/sonovel/parser/BookParser.java → src/main/java/com/pcdd/sonovel/core/Source.java
- `ChapterParser` --inherits--> `Source`  [EXTRACTED]
  src/main/java/com/pcdd/sonovel/parser/ChapterParser.java → src/main/java/com/pcdd/sonovel/core/Source.java
- `SearchParser` --inherits--> `Source`  [EXTRACTED]
  src/main/java/com/pcdd/sonovel/parser/SearchParser.java → src/main/java/com/pcdd/sonovel/core/Source.java
- `TocParser` --inherits--> `Source`  [EXTRACTED]
  src/main/java/com/pcdd/sonovel/parser/TocParser.java → src/main/java/com/pcdd/sonovel/core/Source.java

## Import Cycles
- None detected.

## Communities (33 total, 12 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.09
Nodes (15): AggregatedSearchAction, AggregatedSearchTest, DownloadAction, SingleSearchAction, Source, Double, SearchResultsHandler, List (+7 more)

### Community 1 - "Community 1"
Cohesion: 0.12
Nodes (13): Chapter, ContentType, HtmlExtractor, Document, Element, Elements, Exception, Toc (+5 more)

### Community 2 - "Community 2"
Cohesion: 0.07
Nodes (12): BatchDownloadAction, ShowSourcesAction, ChapterFilter, FilterBuilder, ChapterFormatter, ChapterRenderer, Crawler, TuiLauncher (+4 more)

### Community 3 - "Community 3"
Cohesion: 0.10
Nodes (14): Charset, BookContext, File, CrawlerPostHandler, EpubMergeHandler, HtmlTocHandler, PdfMergeHandler, PostHandlerFactory (+6 more)

### Community 4 - "Community 4"
Cohesion: 0.13
Nodes (16): HttpServlet, HttpServletRequest, HttpServletResponse, LocalBookItem, Override, Serializable, AggregatedSearchServlet, BookDeleteServlet (+8 more)

### Community 5 - "Community 5"
Cohesion: 0.10
Nodes (11): Builder, HttpClientContext, OkHttpClientFactory, DSLParser, Result, DownloadProgressInfo, Search, OkHttpClient (+3 more)

### Community 6 - "Community 6"
Cohesion: 0.12
Nodes (9): TxtMergerTest, LogLevel, Object, RepeatedTest, SneakyThrows, Throwable, FileUtils, JsCaller (+1 more)

### Community 7 - "Community 7"
Cohesion: 0.09
Nodes (9): AutoCloseable, StepEngine, DslBootstrap, ExecutorRegistry, StepExecutor, JavaExecutor, JavaScriptExecutor, VirtualThreadTest (+1 more)

### Community 8 - "Community 8"
Cohesion: 0.14
Nodes (9): Step, Function, JsonResponse, BookParser, String, T, ChineseConverter, CoverUpdater (+1 more)

### Community 9 - "Community 9"
Cohesion: 0.15
Nodes (5): CheckUpdateAction, AppConfigLoader, Props, Setting, LangUtils

### Community 10 - "Community 10"
Cohesion: 0.12
Nodes (8): CliLauncher, VersionProvider, ClientReport, ClientReportRepository, Runnable, ServletContextHandler, Main, WebServer

### Community 11 - "Community 11"
Cohesion: 0.32
Nodes (6): CsvSource, DisplayName, ParameterizedTest, BookSourceCrawlTest, EncodingGarbledTest, ValueSource

### Community 12 - "Community 12"
Cohesion: 0.24
Nodes (6): Entry, Integer, Map, TocList, BookSourceQualityTest, SourceQuality

### Community 13 - "Community 13"
Cohesion: 0.46
Nodes (7): copy_files(), download_jre(), extract_jre(), main(), package_artifacts(), run_maven(), release-windows.sh script

## Knowledge Gaps
- **11 isolated node(s):** `fetch-github-releases.sh script`, `linux-install.sh script`, `release-linux.sh script`, `release-macos.sh script`, `run-linux.sh script` (+6 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **12 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `AppConfig` connect `Community 2` to `Community 0`, `Community 1`, `Community 3`, `Community 4`, `Community 5`, `Community 8`, `Community 9`, `Community 10`, `Community 11`?**
  _High betweenness centrality (0.079) - this node is a cross-community bridge._
- **Why does `Book` connect `Community 3` to `Community 0`, `Community 1`, `Community 2`, `Community 6`, `Community 8`, `Community 10`, `Community 11`, `Community 12`?**
  _High betweenness centrality (0.049) - this node is a cross-community bridge._
- **Why does `SearchResult` connect `Community 0` to `Community 1`, `Community 2`, `Community 4`, `Community 5`, `Community 8`, `Community 10`, `Community 11`?**
  _High betweenness centrality (0.021) - this node is a cross-community bridge._
- **What connects `fetch-github-releases.sh script`, `linux-install.sh script`, `release-linux.sh script` to the rest of the system?**
  _11 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Community 0` be split into smaller, more focused modules?**
  _Cohesion score 0.08672699849170437 - nodes in this community are weakly interconnected._
- **Should `Community 1` be split into smaller, more focused modules?**
  _Cohesion score 0.12 - nodes in this community are weakly interconnected._
- **Should `Community 2` be split into smaller, more focused modules?**
  _Cohesion score 0.06956521739130435 - nodes in this community are weakly interconnected._