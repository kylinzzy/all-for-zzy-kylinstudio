#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从《密室大逃脱各季播出数据统计表.xlsx》提取前7季 + 第8季行标签/基线，
构建 seasons_compare_template.json 静态模板。

- 前7季播放量：Excel 原值（单位统一为「万」），不可修改。
- 第8季：仅保留 Excel 已填的前几期作为基线；渲染时由 export_site.py 用
  芒果TV API 实时数据覆盖「已采集期」，未播期保持 null -> 页面显示「-」。
"""
import json
import re
import openpyxl

SRC_XLSX = "/Users/kylinwu/Downloads/密室大逃脱各季播出数据统计表.xlsx"
OUT = "/Users/kylinwu/Documents/腾讯ai/Claw/seasons_compare_template.json"

SEASONS = ["第1季", "第2季", "第3季", "第4季", "第5季", "第6季", "第7季", "第8季"]
# Excel 列索引：A=0..G=6 为第1~7季，H=7 内容类型，I=8 第8季，M=12 关键节点
COL_TYPE = 7
COL_S8 = 8
COL_NOTE = 12


def parse_play(s):
    if s is None:
        return None
    s = str(s).strip()
    if s in ("", "N/A", "None", "none"):
        return None
    m = re.match(r"([\d.]+)\s*亿", s)
    if m:
        return round(float(m.group(1)) * 10000, 1)
    m = re.match(r"([\d.]+)\s*万", s)
    if m:
        return round(float(m.group(1)), 1)
    try:
        return round(float(s), 1)
    except ValueError:
        return None


def main():
    wb = openpyxl.load_workbook(SRC_XLSX, data_only=True)
    ws = wb["1.密逃1-8季播放量数据"]

    rows = []
    notes = []  # 第8季关键节点（M列非空项，跨行分布）
    for r in ws.iter_rows(values_only=True):
        # 关键节点列（M）可能独立成行，也可能与数据行同行 -> 每行先收集
        if len(r) > COL_NOTE and r[COL_NOTE] not in (None, ""):
            t = str(r[COL_NOTE]).strip()
            if t != "关键节点" and t not in notes:
                notes.append(t)

        # 跳过表头行与空行
        ctype = r[COL_TYPE]
        if ctype is None:
            continue
        ctype = str(ctype).strip()
        if ctype in ("内容类型（启播日为第一期正片日）", "内容类型\n（启播日为第一期正片日）", "播放量", "内容类型"):
            continue
        if ctype == "":
            continue

        plays = {}
        for i, season in enumerate(SEASONS[:7]):
            plays[season] = parse_play(r[i])  # A..G
        plays["第8季"] = parse_play(r[COL_S8])  # I

        summary = None
        if "总播放量" in ctype:
            summary = "total"
        elif "集均" in ctype:
            summary = "avg"

        rows.append({
            "type": ctype,
            "plays": plays,
            "summary": summary,
        })

    out = {
        "seasons": SEASONS,
        "note_title": "关键节点",
        "notes": notes,
        "rows": rows,
    }

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"[build] -> {OUT}")
    print(f"[build] rows={len(rows)} notes={len(notes)}")
    # 校验：打印前几行与第8季非空头
    for row in rows:
        s8 = row["plays"].get("第8季")
        if s8 is not None:
            print(f"  第8季已填: {row['type']} = {s8}万")
    print("  关键节点:", notes)


if __name__ == "__main__":
    main()
