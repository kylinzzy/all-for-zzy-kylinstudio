#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""导出对外发布的 site/data.json（前端实时渲染用）。

从 episode_data.json 提取精简公开字段，供 GitHub Pages 上的 index.html 实时拉取。
不暴露采集历史明细等内部字段，只保留展示所需数据。
"""
import json
import os
import re
import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(BASE, 'episode_data.json')
SITE_DIR = os.path.join(BASE, 'site')
OUT = os.path.join(SITE_DIR, 'data.json')
TEMPLATE = os.path.join(BASE, 'seasons_compare_template.json')


def s8_ep_name(ctype):
    """内容类型行 -> 芒果TV API 中对应的集名（用于实时填充第8季）。"""
    if '超前聚会上' in ctype:
        return '超前聚会(上)'
    if '超前聚会下' in ctype:
        return '超前聚会(下)'
    if '收官' in ctype:
        return None  # 收官暂无单独API集，后续上播再补
    m = re.search(r'第(\d+)期.*?(上|下)', ctype)
    return f'第{m.group(1)}期({m.group(2)})' if m else None


def build_seasons_compare(template, eps):
    """用实时抓取数据填充第8季，并动态计算第8季总计/集均。

    前7季保持 Excel 静态原值不动；第8季实时优先、基线兜底。
    """
    name_plays = {e.get('name', ''): float(e.get('current_playcount_wan') or 0)
                  for e in eps.values()}

    # 第一遍：累计第8季正片实时合计与期数
    s8_total = 0.0
    s8_periods = set()
    for row in template['rows']:
        ctype = row['type']
        ep_name = s8_ep_name(ctype)
        if ep_name and ep_name in name_plays and '正片' in ctype:
            val = name_plays[ep_name]
            if val:
                s8_total += val
                m = re.search(r'第(\d+)期', ctype)
                if m:
                    s8_periods.add(int(m.group(1)))

    # 第二遍：构建渲染用 rows
    rows = []
    for row in template['rows']:
        ctype = row['type']
        plays = dict(row['plays'])
        ep_name = s8_ep_name(ctype)
        s8_live = name_plays.get(ep_name) if ep_name else None
        s8_base = plays.get('第8季')

        if row.get('summary') == 'total':
            plays['第8季'] = round(s8_total, 1) if s8_total else None
        elif row.get('summary') == 'avg':
            plays['第8季'] = round(s8_total / len(s8_periods), 1) if s8_periods else None
        else:
            # 实时优先，Excel 基线兜底
            plays['第8季'] = s8_live if (s8_live not in (None, 0)) else s8_base
        rows.append({'type': ctype, 'plays': plays, 'summary': row.get('summary')})

    return {
        'seasons': template['seasons'],
        'notes': template.get('notes', []),
        'rows': rows,
    }


def main():
    with open(SRC, encoding='utf-8') as f:
        d = json.load(f)

    meta = d.get('metadata', {})
    eps = d.get('episodes', {})
    milestones = d.get('milestones') or d.get('episode_milestones') or {}

    # 各季同比表（前7季静态 + 第8季实时填充）
    seasons_compare = None
    if os.path.exists(TEMPLATE):
        with open(TEMPLATE, encoding='utf-8') as tf:
            seasons_compare = build_seasons_compare(json.load(tf), eps)
    else:
        print('[warn] 未找到 seasons_compare_template.json，跳过同比表')
    # 兼容扁平结构 {日期: 万数} 与嵌套结构 {data:{日期:{...}}}
    _dpp = d.get('daily_platform_plays', {}) or {}
    daily_raw = _dpp.get('data', _dpp) if isinstance(_dpp, dict) else {}
    psum = d.get('platform_summary', {})

    # 单集列表
    episodes = []
    total_wan = 0.0
    for vid, ep in eps.items():
        pw = float(ep.get('current_playcount_wan', 0) or 0)
        total_wan += pw
        episodes.append({
            'video_id': vid,
            'serialno': int(ep.get('serialno', 0) or 0),
            'name': ep.get('name', ''),
            'title': ep.get('title', ''),
            'launch': ep.get('launch', ''),
            'plays_wan': pw,
            'plays_text': ep.get('current_playcount_text', ''),
            'vip': bool(ep.get('vip', False)),
            'last_collect_time': ep.get('last_collect_time', ''),
            'hist_count': len(ep.get('collection_history', [])),
        })
    episodes.sort(key=lambda x: x['serialno'])

    # 里程碑扁平化
    name_map = {vid: e.get('name', '') for vid, e in eps.items()}
    serial_map = {vid: int(e.get('serialno', 0) or 0) for vid, e in eps.items()}
    ms_list = []
    for vid, nodes in milestones.items():
        if not isinstance(nodes, list):
            continue
        for n in nodes:
            ms_list.append({
                'video_id': vid,
                'name': name_map.get(vid, ''),
                'serialno': serial_map.get(vid, 0),
                'node_wan': n.get('node_wan'),
                'node_yi': n.get('node_yi'),
                'status': n.get('status'),
                'achieve_time': n.get('achieve_time'),
                'detected_at': n.get('detected_at'),
            })
    ms_list.sort(key=lambda x: (x['serialno'], x['node_wan'] or 0))

    # 每日平台播放量（兼容 v 为数字 或 {plays_wan,...} 两种形态）
    daily = []
    for date, v in daily_raw.items():
        if isinstance(v, dict):
            pw = float(v.get('plays_wan', 0) or 0)
            wd = v.get('weekday', '') or ''
            note = v.get('note', '') or ''
            is_upd = bool(v.get('is_update', False))
        else:
            pw = float(v or 0)
            wd = ''
            note = ''
            is_upd = False
        daily.append({
            'date': date,
            'weekday': wd,
            'plays_wan': pw,
            'is_update': is_upd,
            'note': note,
        })
    daily.sort(key=lambda x: x['date'])

    out = {
        'meta': {
            'collection_name': meta.get('collection_name', ''),
            'collection_url': meta.get('collection_url', ''),
            'last_collect_time': meta.get('last_collect_time', ''),
            'total_collections': meta.get('total_collections', 0),
            'episode_count': len(episodes),
            'total_wan': round(total_wan, 1),
            'platform_cumulative_yi': psum.get('cumulative_yi'),
            'platform_cumulative_wan': psum.get('cumulative_wan'),
            'data_source': psum.get('data_source', ''),
            'generated_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        },
        'episodes': episodes,
        'milestones': ms_list,
        'daily': daily,
        'platform_summary': {
            'cumulative_yi': psum.get('cumulative_yi'),
            'cumulative_wan': psum.get('cumulative_wan'),
            'yesterday_plays_yi': psum.get('yesterday_plays_yi'),
            'data_source': psum.get('data_source', ''),
            'last_update': psum.get('last_update', ''),
        },
        'historical_milestones': d.get('historical_milestones', []),
        'seasons_compare': seasons_compare,
    }

    os.makedirs(SITE_DIR, exist_ok=True)
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    sc_rows = len(seasons_compare['rows']) if seasons_compare else 0
    print(f'[export] -> {OUT}')
    print(f'[export] episodes={len(episodes)} milestones={len(ms_list)} daily={len(daily)} total_wan={total_wan:.1f} seasons_compare_rows={sc_rows}')


if __name__ == '__main__':
    main()
