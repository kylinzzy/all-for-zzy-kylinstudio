#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""云端 headless 采集的原始 JSON -> site/maoyan_data.json（前端猫眼专用数据源）。

同时回写 episode_data.json 的 platform_summary / daily_platform_plays / honor_moments，
供 export_site.py 生成 site/data.json 时带新鲜猫眼数据（保留 historical_milestones 等其它字段）。

输入：collect_maoyan_cloud.js 输出的原始 JSON（参数1，默认 /tmp/maoyan_raw.json）
输出：site/maoyan_data.json + 更新 episode_data.json
"""
import json
import os
import sys
import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
SRC_JSON = sys.argv[1] if len(sys.argv) > 1 else '/tmp/maoyan_raw.json'
EPISODE = os.path.join(BASE, 'episode_data.json')
SITE_OUT = os.path.join(BASE, 'site', 'maoyan_data.json')
WEEKDAY = ['星期一', '星期二', '星期三', '星期四', '星期五', '星期六', '星期日']


def derive_breakthroughs(daily, cum_yi):
    """按每日播放量累加，定位首次跨过 X 亿的日期；里程碑只到官方累计已破的最大整数亿。"""
    items = sorted(daily.items())
    cum = 0.0
    reach_date = {}
    for date, wan in items:
        if wan is None:
            continue
        cum += wan
        for x in range(1, 200):
            if x not in reach_date and cum >= x * 10000:  # x亿 = x*10000万
                reach_date[x] = date
    bt = []
    for x in range(1, int(cum_yi or 0) + 1):
        bt.append({'yi': x, 'date': reach_date.get(x, ''),
                   'cumulative_yi': x, 'desc': f'累计播放量破{x}亿'})
    return bt


def main():
    with open(SRC_JSON, encoding='utf-8') as f:
        raw = json.load(f)

    cum_yi = raw.get('cumulative_yi')
    today_wan = raw.get('today_wan')
    yes_yi = raw.get('yesterday_yi')
    daily = raw.get('daily', {})
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # 每日明细数组（日期倒序：最新在前，与看板显示一致）
    arr = []
    for date, v in daily.items():
        if not isinstance(date, str) or not date[:4].isdigit():
            continue
        try:
            dt = datetime.datetime.strptime(date, '%Y-%m-%d')
        except Exception:
            continue
        arr.append({
            'date': date,
            'weekday': WEEKDAY[dt.weekday()],
            'plays_wan': round(float(v or 0), 1),
            'is_update': False,
            'note': '',
        })
    arr.sort(key=lambda x: x['date'], reverse=True)  # 倒序：最新在前

    ps = {
        'cumulative_yi': cum_yi,
        'cumulative_wan': round((cum_yi or 0) * 10000, 1) if cum_yi else None,
        'yesterday_plays_yi': yes_yi,
        'today_realtime_wan': today_wan,
        'data_source': '猫眼专业版-平台表现(云端 headless 自动化)',
        'last_update': now,
        'data_status': 'normal',
        'description': '平台总数据摘要，来自猫眼专业版（云端浏览器采集）',
        'daily_platform_plays': daily,
    }
    bt = derive_breakthroughs(daily, cum_yi)
    honor = {'breakthroughs': bt, 'heat_champion_days': 0}
    ps['honor_moments'] = honor

    out = {
        'meta': {
            'last_collect_time': now,
            'data_source': ps['data_source'],
            'generated_at': now,
            'note': '猫眼数据由云端 headless 浏览器每小时自动采集后推送，不依赖本机。',
        },
        'platform_summary': {
            'cumulative_yi': cum_yi,
            'cumulative_wan': ps['cumulative_wan'],
            'yesterday_plays_yi': yes_yi,
            'today_realtime_wan': today_wan,
            'data_source': ps['data_source'],
            'last_update': now,
            'data_status': 'normal',
        },
        'daily_platform_plays': daily,
        'daily': arr,
        'honor_moments': honor,
    }
    os.makedirs(os.path.dirname(SITE_OUT), exist_ok=True)
    with open(SITE_OUT, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f'[build_maoyan] -> {SITE_OUT} 累计={cum_yi}亿 今日={today_wan}万 '
          f'明细={len(arr)}天 破亿={len(bt)}项')

    # 回写 episode_data.json（保留其它字段，含 historical_milestones）
    store = {}
    if os.path.exists(EPISODE):
        try:
            store = json.load(open(EPISODE, encoding='utf-8'))
        except Exception:
            store = {}
    old_ps = store.get('platform_summary', {})
    new_ps = dict(old_ps)
    new_ps.update(ps)
    store['platform_summary'] = new_ps
    store['daily_platform_plays'] = daily
    with open(EPISODE, 'w', encoding='utf-8') as f:
        json.dump(store, f, ensure_ascii=False, indent=2)
    print('[build_maoyan] episode_data.json platform_summary 已回写')


if __name__ == '__main__':
    main()
