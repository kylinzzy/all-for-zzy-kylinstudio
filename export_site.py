#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""导出对外发布的 site/data.json（前端实时渲染用）。

从 episode_data.json 提取精简公开字段，供 GitHub Pages 上的 index.html 实时拉取。
不暴露采集历史明细等内部字段，只保留展示所需数据。
"""
import json
import os
import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(BASE, 'episode_data.json')
SITE_DIR = os.path.join(BASE, 'site')
OUT = os.path.join(SITE_DIR, 'data.json')


def main():
    with open(SRC, encoding='utf-8') as f:
        d = json.load(f)

    meta = d.get('metadata', {})
    eps = d.get('episodes', {})
    milestones = d.get('milestones') or d.get('episode_milestones') or {}
    daily_raw = d.get('daily_platform_plays', {}).get('data', {})
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

    # 每日平台播放量
    daily = []
    for date, v in daily_raw.items():
        daily.append({
            'date': date,
            'weekday': v.get('weekday', ''),
            'plays_wan': float(v.get('plays_wan', 0) or 0),
            'is_update': bool(v.get('is_update', False)),
            'note': v.get('note', ''),
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
    }

    os.makedirs(SITE_DIR, exist_ok=True)
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f'[export] -> {OUT}')
    print(f'[export] episodes={len(episodes)} milestones={len(ms_list)} daily={len(daily)} total_wan={total_wan:.1f}')


if __name__ == '__main__':
    main()
