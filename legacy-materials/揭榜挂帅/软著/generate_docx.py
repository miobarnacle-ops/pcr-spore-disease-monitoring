#!/usr/bin/env python3
"""
Generate source code document for software copyright application.
Software: 多模态农田孢子监测与病害扩散预警系统 V1.0

Format:
  - 50 lines per page, 60 pages total (first 30 + last 30 of full doc)
  - Header: software full name + version + page number
  - Times New Roman 10.5pt, 15pt exact line spacing
  - Blank lines and comments already removed in compliance file
  - Long lines broken at logical points to avoid wrapping
  - Matches reference document format
"""

import os
import sys
from docx import Document
from docx.shared import Pt, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import nsdecls
from docx.oxml import parse_xml

# ============================================================
# Configuration
# ============================================================
SOFTWARE_NAME = "多模态农田孢子监测与病害扩散预警系统"
VERSION = "V1.0"
FULL_HEADER = SOFTWARE_NAME + " " + VERSION

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SOURCE_FILE = os.path.join(BASE_DIR, "main_inspection_system_v4_compliance.py")
TEMPLATE_FILE = os.path.join(
    BASE_DIR, "基于深度强化学习的农业采摘机器人控制软件V1.0.docx"
)
OUTPUT_FILE = os.path.join(
    BASE_DIR, "多模态农田孢子监测与病害扩散预警系统V1.0_源代码文档.docx"
)

FONT_NAME = "Times New Roman"
FONT_SIZE = Pt(10.5)
HEADER_FONT_SIZE = Pt(9)
LINE_SPACING = Pt(15)
MAX_CHARS_PER_LINE = 82
LINES_PER_PAGE = 50
PAGES_FIRST_HALF = 30
PAGES_LAST_HALF = 30


def read_source_lines(filepath):
    """Read source file, remove blank lines. Comments already removed."""
    with open(filepath, "r", encoding="utf-8") as f:
        raw = f.readlines()

    lines = []
    for line in raw:
        stripped = line.rstrip()
        if stripped:
            lines.append(stripped)
    return lines


def find_break_point(line, max_chars):
    """Find the best position to break a line at or before max_chars."""
    if len(line) <= max_chars:
        return len(line)

    search_start = max(0, max_chars - 25)
    segment = line[:max_chars]

    break_after = [
        ", ", " + ", " - ", " * ", " / ", " // ",
        " and ", " or ", " if ", " else ",
        " == ", " != ", " >= ", " <= ", " > ", " < ",
        " = ", " (", " & ", " | ",
    ]

    best = -1
    for sep in break_after:
        pos = segment.rfind(sep, search_start)
        if pos > best:
            best = pos + len(sep)

    if best <= 0:
        pos = segment.rfind(" ", search_start)
        if pos > 0:
            best = pos + 1
        else:
            best = max_chars

    return best


def break_long_line(line, max_chars):
    """Break a long line into segments, each within max_chars."""
    if len(line) <= max_chars:
        return [line]

    base_indent = len(line) - len(line.lstrip())
    cont_indent = base_indent + 8

    segments = []
    remaining = line

    while len(remaining) > max_chars:
        bp = find_break_point(remaining, max_chars)
        seg = remaining[:bp].rstrip()
        if seg:
            segments.append(seg)
        remaining = (" " * cont_indent) + remaining[bp:].lstrip()

    if remaining.strip():
        segments.append(remaining)

    return segments


def setup_header(section):
    """Configure the page header with software name, version, and page number."""
    header = section.header
    header.is_linked_to_previous = False

    hp = header.paragraphs[0]
    hp.clear()
    hp.alignment = WD_ALIGN_PARAGRAPH.LEFT

    # Software name
    rn = hp.add_run(SOFTWARE_NAME)
    rn.font.name = FONT_NAME
    rn.font.size = HEADER_FONT_SIZE

    # Space then version
    rv = hp.add_run("    " + VERSION + "       ")
    rv.font.name = FONT_NAME
    rv.font.size = HEADER_FONT_SIZE

    # PAGE field for auto-numbering
    fld_begin = parse_xml(
        '<w:fldChar {} w:fldCharType="begin"/>'.format(nsdecls("w"))
    )
    fld_instr = parse_xml(
        '<w:instrText {} xml:space="preserve"> PAGE </w:instrText>'.format(
            nsdecls("w")
        )
    )
    fld_sep = parse_xml(
        '<w:fldChar {} w:fldCharType="separate"/>'.format(nsdecls("w"))
    )
    fld_end = parse_xml(
        '<w:fldChar {} w:fldCharType="end"/>'.format(nsdecls("w"))
    )

    rp = hp.add_run()
    rp.font.name = FONT_NAME
    rp.font.size = HEADER_FONT_SIZE
    rp._r.append(fld_begin)
    rp._r.append(fld_instr)
    rp._r.append(fld_sep)
    rp._r.append(fld_end)

    # Right-align tab stop for the page number area
    hp.paragraph_format.tab_stops.add_tab_stop(Cm(15.75))


def setup_page(doc):
    """Configure page dimensions, margins, and styles."""
    section = doc.sections[0]
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.left_margin = Cm(2.75)
    section.right_margin = Cm(2.5)
    section.top_margin = Cm(1.5)
    section.bottom_margin = Cm(1.5)
    section.header_distance = Cm(1.0)

    style = doc.styles["Normal"]
    style.font.name = FONT_NAME
    style.font.size = FONT_SIZE
    style.paragraph_format.line_spacing = LINE_SPACING
    style.paragraph_format.space_before = Pt(0)
    style.paragraph_format.space_after = Pt(0)

    setup_header(section)


def add_code_line(doc, text):
    """Add a single code line as a formatted paragraph."""
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.line_spacing = LINE_SPACING
    pf.space_before = Pt(0)
    pf.space_after = Pt(0)
    pf.widow_control = False

    run = p.add_run(text)
    run.font.name = FONT_NAME
    run.font.size = FONT_SIZE
    return p


def main():
    print("=" * 60)
    print("软著源代码文档生成工具")
    print(f"软件名称: {FULL_HEADER}")
    print(f"源文件: {os.path.basename(SOURCE_FILE)}")
    print("=" * 60)

    # Step 1: Read source
    print("\n[1/3] 读取源代码...")
    source_lines = read_source_lines(SOURCE_FILE)
    print(f"  有效代码行数: {len(source_lines)}")

    # Step 2: Break long lines
    print(f"\n[2/3] 处理超长行 (限制 {MAX_CHARS_PER_LINE} 字符/行)...")
    processed = []
    broken_count = 0
    for line in source_lines:
        segments = break_long_line(line, MAX_CHARS_PER_LINE)
        if len(segments) > 1:
            broken_count += 1
        processed.extend(segments)

    print(f"  处理后总行数: {len(processed)}")
    print(f"  拆分的超长行: {broken_count}")

    total_pages = (len(processed) + LINES_PER_PAGE - 1) // LINES_PER_PAGE
    print(f"  完整文档页数: {total_pages} (每页 {LINES_PER_PAGE} 行)")

    # Verify
    over = [(i, len(l)) for i, l in enumerate(processed)
            if len(l) > MAX_CHARS_PER_LINE]
    if over:
        print(f"  *** 警告: {len(over)} 行仍超限! ***")
        for i, length in over[:5]:
            print(f"    行 {i}: {length} 字符")

    # Step 3: Select 60 pages (first 30 + last 30)
    print(f"\n[3/3] 生成 60 页提交文档 (前{PAGES_FIRST_HALF}页 + 后{PAGES_LAST_HALF}页)...")
    lines_per_half = LINES_PER_PAGE * PAGES_FIRST_HALF  # 1500

    if len(processed) > lines_per_half * 2:
        selected = (processed[:lines_per_half] +
                    processed[-lines_per_half:])
        print(f"  选取前 {lines_per_half} 行 + 后 {lines_per_half} 行")
    else:
        selected = processed
        print(f"  全部选取 ({len(selected)} 行)")

    print(f"  提交行数: {len(selected)}")

    # Create document
    if os.path.exists(TEMPLATE_FILE):
        doc = Document(TEMPLATE_FILE)
        # Remove template content
        body = doc.element.body
        for p in doc.paragraphs:
            p._element.getparent().remove(p._element)
    else:
        doc = Document()

    setup_page(doc)

    for idx, line in enumerate(selected):
        p = add_code_line(doc, line)
        # Set page_break_before on first line of each new page (pages 2-60)
        if idx > 0 and idx % LINES_PER_PAGE == 0:
            p.paragraph_format.page_break_before = True
        if (idx + 1) % 500 == 0:
            print(f"    已写入 {idx + 1}/{len(selected)} 行...")

    doc.save(OUTPUT_FILE)

    print(f"\n{'=' * 60}")
    print(f"文档生成成功!")
    print(f"输出: {OUTPUT_FILE}")
    print(f"总行数: {len(selected)}")
    print(f"总页数: 60 (精确 {LINES_PER_PAGE} 行/页)")
    print(f"格式: {FONT_NAME} {FONT_SIZE}, 行距 {LINE_SPACING}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
