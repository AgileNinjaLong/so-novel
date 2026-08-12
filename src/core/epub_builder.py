import os
import zipfile
import html
from typing import List, Dict

class EpubBuilder:
    @staticmethod
    def build_epub(title: str, author: str, chapters: List[Dict[str, str]], output_path: str):
        """原生生成标准的 EPUB 电子书 (Zip 容器，含 mimetype, container.xml, content.opf, toc.ncx, XHTML 章节)"""
        with zipfile.ZipFile(output_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
            # 1. mimetype (必须为无压缩存入的首个文件)
            zf.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)

            # 2. META-INF/container.xml
            container_xml = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
   <rootfiles>
      <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
   </rootfiles>
</container>"""
            zf.writestr("META-INF/container.xml", container_xml)

            # 3. 生成各个章节的 XHTML 文件
            manifest_items = []
            spine_itemrefs = []
            nav_points = []

            safe_title = html.escape(title or "未知书名")
            safe_author = html.escape(author or "未知作者")

            for idx, chap in enumerate(chapters, start=1):
                chap_title = chap.get("title", f"第{idx}章")
                safe_chap_title = html.escape(chap_title)
                raw_content = chap.get("content", "")
                
                # 将文本拆分为 <p> 标签
                paragraphs = raw_content.splitlines()
                p_html = "".join([f"<p>{html.escape(line.strip())}</p>" for line in paragraphs if line.strip()])
                
                chap_filename = f"chapter_{idx}.xhtml"
                chap_xhtml = f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
  <title>{safe_chap_title}</title>
  <style type="text/css">
    body {{ font-family: sans-serif; margin: 5%; }}
    h2 {{ text-align: center; margin-bottom: 2em; }}
    p {{ text-indent: 2em; line-height: 1.6; margin-top: 0.5em; margin-bottom: 0.5em; }}
  </style>
</head>
<body>
  <h2>{safe_chap_title}</h2>
  {p_html}
</body>
</html>"""
                zf.writestr(f"OEBPS/{chap_filename}", chap_xhtml)

                manifest_items.append(f'<item id="chap_{idx}" href="{chap_filename}" media-type="application/xhtml+xml"/>')
                spine_itemrefs.append(f'<itemref idref="chap_{idx}"/>')
                nav_points.append(f"""    <navPoint id="navPoint-{idx}" playOrder="{idx}">
      <navLabel><text>{safe_chap_title}</text></navLabel>
      <content src="{chap_filename}"/>
    </navPoint>""")

            # 4. OEBPS/toc.ncx
            ncx_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE ncx PUBLIC "-//NISO//DTD NCX 2005-1//EN" "http://www.daisy.org/z3986/2005/ncx-2005-1.dtd">
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head>
    <meta name="dtb:uid" content="urn:uuid:novelread-{hash(title)}"/>
    <meta name="dtb:depth" content="1"/>
    <meta name="dtb:totalPageCount" content="0"/>
    <meta name="dtb:maxPageNumber" content="0"/>
  </head>
  <docTitle><text>{safe_title}</text></docTitle>
  <navMap>
{"\n".join(nav_points)}
  </navMap>
</ncx>"""
            zf.writestr("OEBPS/toc.ncx", ncx_xml)

            # 5. OEBPS/content.opf
            opf_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="BookId" version="2.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:title>{safe_title}</dc:title>
    <dc:creator opf:role="aut">{safe_author}</dc:creator>
    <dc:language>zh-CN</dc:language>
    <dc:identifier id="BookId">urn:uuid:novelread-{hash(title)}</dc:identifier>
  </metadata>
  <manifest>
    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
{"\n".join(manifest_items)}
  </manifest>
  <spine toc="ncx">
{"\n".join(spine_itemrefs)}
  </spine>
</package>"""
            zf.writestr("OEBPS/content.opf", opf_xml)
