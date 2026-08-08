#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""猫眼专业版《密室大逃脱第8季》平台表现数据自动采集。

鉴权方式（已破解，无需登录 cookie）：
  1. GET 页面 https://piaofang.maoyan.com/i/tv-datainfo/1607407/platform
  2. 从 HTML <meta> 标签提取 csrf + deviceId
  3. GET /i/api/netWorkPlatFrom/getPlatData?seriesId=1607407&isShow=true&platformType=1
     Headers: uid=<csrf>, uuid=<deviceId>
  4. GET /i/api/maoyanHeat/getAllData?seriesId=1607407  （猫眼热度排名）

数据写入 episode_data.json 的 platform_summary：
  cumulative_yi / cumulative_wan  : 累计播放量（亿/万）
  yesterday_plays_yi             : 昨日播放量（亿）
  today_realtime_wan             : 今日实时播放量（万）
  daily_platform_plays           : 每日播放量明细（日期->万）
  honor_moments                 : 荣誉时刻（日冠天数 + 破亿节点）
  data_source                    : 数据来源标记
  last_update                    : 更新时间
"""
import json
import os
import re
import datetime
import urllib.request
import urllib.error

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE, "episode_data.json")
SERIES_ID = 1607407
PAGE_URL = f"https://piaofang.maoyan.com/i/tv-datainfo/{SERIES_ID}/platform?barTheme=424242"
API_PATH = f"/i/api/netWorkPlatFrom/getPlatData?seriesId={SERIES_ID}&isShow=true&platformType=1"
HEAT_PATH = f"/i/api/maoyanHeat/getAllData?seriesId={SERIES_ID}"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def fetch_page_meta():
    """抓取页面HTML，提取 csrf 和 deviceId"""
    req = urllib.request.Request(PAGE_URL, headers={
        "User-Agent": UA,
        "Referer": "https://piaofang.maoyan.com/",
        "Accept": "text/html",
    })
    html = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", "replace")

    csrf = None
    device_id = None
    for m in re.finditer(r'<meta[^>]+name=["\']([^"\']+)["\'][^>]*content=["\']([^"\']*)["\']', html):
        name, val = m.group(1), m.group(2)
        if name == "csrf":
            csrf = val
        elif name == "deviceId":
            device_id = val

    if not csrf or not device_id:
        print(f"[maoyan] 页面缺少 meta 标签: csrf={bool(csrf)}, deviceId={bool(device_id)}")
        return None, None
    return csrf, device_id


def fetch_api(csrf, device_id):
    """调用猫眼平台表现 API"""
    url = f"https://piaofang.maoyan.com{API_PATH}"
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Referer": PAGE_URL,
        "Accept": "application/json, text/plain, */*",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": "https://piaofang.maoyan.com",
        "uid": csrf,
        "uuid": device_id,
    })
    try:
        raw = urllib.request.urlopen(req, timeout=15).read()
        return json.loads(raw.decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:300]
        print(f"[maoyan] HTTP {e.code}: {body}")
        return None


def fetch_heat_api(csrf, device_id):
    """调用猫眼热度排名 API（用于计算日冠天数）"""
    url = f"https://piaofang.maoyan.com{HEAT_PATH}"
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Referer": PAGE_URL,
        "Accept": "application/json, text/plain, */*",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": "https://piaofang.maoyan.com",
        "uid": csrf,
        "uuid": device_id,
    })
    try:
        raw = urllib.request.urlopen(req, timeout=15).read()
        return json.loads(raw.decode("utf-8", "replace"))
    except Exception as e:
        print(f"[maoyan] heat API error: {str(e)[:120]}")
        return None


def derive_honor_moments(daily_plays, heat_data=None):
    """从每日播放量和热度排名推导荣誉时刻。

    Returns:
      {
        'heat_champion_days': int,       # 猫眼热度日冠天数
        'heat_champion_first': str,      # 首次日冠日期
        'breakthroughs': [               # 破亿节点列表
          {'yi': 11, 'date': '2026-08-05', 'desc': '累计播放量破11亿'},
          ...
        ]
      }
    """
    result = {"heat_champion_days": 0, "heat_champion_first": "", "breakthroughs": []}

    # --- 日冠天数：从热度排名数据中统计 rank==1 的天数 ---
    if heat_data:
        try:
            rows = heat_data.get("data", {}).get("tableData", [])
            day1_rows = [r for r in rows if r.get("currHeatRank") == 1]
            result["heat_champion_days"] = len(day1_rows)
            if day1_rows:
                first_date = day1_rows[0].get("dateTimeDesc", "")
                result["heat_champion_first"] = first_date
            print(f"[maoyan] 热度日冠: {len(day1_rows)}天"
                  f"{' 首次:' + first_date if first_date else ''}")
        except Exception as e:
            print(f"[maoyan] heat parse warn: {e}")

    # --- 破亿节点：累加每日净网播播放量 ---
    if daily_plays:
        sorted_dates = sorted(daily_plays.keys())
        cum = 0.0
        prev_cum = 0.0
        for d in sorted_dates:
            val = float(daily_plays[d]) if daily_plays[d] else 0
            cum += val
            # 检查是否跨过整亿门槛 (8~15亿范围)
            for yi in range(8, 16):
                threshold = yi * 10000  # 亿转万
                if prev_cum < threshold <= cum:
                    result["breakthroughs"].append({
                        "yi": yi,
                        "date": d,
                        "cumulative_yi": round(cum / 10000, 2),
                        "desc": f"累计播放量破{yi}亿",
                    })
                    print(f"[maoyan] 破{yi}亿 ≈ {d} (累计{cum/10000:.2f}亿)")
            prev_cum = cum

    # 按亿数降序排列（最新最大在前）
    result["breakthroughs"].sort(key=lambda x: -x["yi"])
    return result


def to_wan(text):
    """'11.61亿' / '3461.8万' -> 万为单位的 float"""
    if not text:
        return None
    m = re.search(r"([\d.]+)\s*(亿|万)?", str(text))
    if not m:
        return None
    val = float(m.group(1))
    if m.group(2) == "亿":
        return val * 10000
    return val


def parse_and_store(api_data, heat_data=None):
    """解析API响应，写入 episode_data.json"""
    data = api_data.get("data", {})
    heat = data.get("networkHeat", {})

    # 累计 / 今日 / 昨日
    cum_val = heat.get("sumPlayCountDesc")
    cum_unit = heat.get("sumPlayCountUnit", "")
    cum_wan = to_wan(f"{cum_val or 0}{cum_unit}") if cum_val else None

    tod_val = heat.get("todayPlayCountDesc")
    tod_unit = heat.get("todayPlayCountUnit", "")
    tod_wan = to_wan(f"{tod_val or 0}{tod_unit}") if tod_val else None

    yes_val = heat.get("yesterdayPlayCountDesc")
    yes_unit = heat.get("yesterdayPlayCountUnit", "")
    yes_yi = to_wan(f"{yes_val or 0}{yes_unit}") / 10000 if yes_val else None

    # 每日明细
    daily = {}
    for row in data.get("rows", []):
        date_str = row.get("dateTimeDesc", "")
        plays = to_wan(row.get("sumPlayCountDesc"))
        if date_str and plays is not None:
            daily[date_str] = round(plays, 1)

    # 荣誉时刻推导（日冠 + 破亿）
    honor = derive_honor_moments(daily, heat_data)

    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    summary = {
        "cumulative_yi": round(cum_wan / 10000, 2) if cum_wan else None,
        "cumulative_wan": round(cum_wan, 1) if cum_wan else None,
        "yesterday_plays_yi": round(yes_yi, 2) if yes_yi else None,
        "today_realtime_wan": round(tod_wan, 1) if tod_wan else None,
        "daily_platform_plays": daily,
        "honor_moments": honor,
        "data_source": "猫眼专业版-平台表现",
        "last_update": now,
    }

    # 写入 episode_data.json
    store = load_data()
    store.setdefault("platform_summary", {})
    store["platform_summary"].update(summary)
    # 也保留 daily_platform_plays 在顶层（供导出用）
    store["daily_platform_plays"] = daily
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, indent=2)

    bt_count = len(honor.get("breakthroughs", []))
    print(f"[maoyan] 累计{summary['cumulative_yi']}亿 | 今日{summary['today_realtime_wan']}万"
          f" | 昨日{summary['yesterday_plays_yi']}亿 | {len(daily)}天明细"
          f" | 日冠{honor['heat_champion_days']}天 | 破亿节点{bt_count}项")
    return summary


def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {"metadata": {}, "episodes": {}, "milestones": {},
            "platform_summary": {}, "daily_platform_plays": {}}


def main():
    print("[maoyan] === 猫眼专业版数据采集开始 ===")

    # Step 1: 获取页面 meta 鉴权凭证
    csrf, device_id = fetch_page_meta()
    if not csrf:
        print("[maoyan] 无法获取 csrf，退出")
        return 1
    print(f"[maoyan] meta: csrf={csrf[:12]}... deviceId={device_id}")

    # Step 2: 调用平台表现 API
    api_data = fetch_api(csrf, device_id)
    if not api_data:
        return 1

    # Step 3: 调用热度排名 API（用于荣誉时刻-日冠）
    heat_data = fetch_heat_api(csrf, device_id)

    # Step 4: 解析存储（含荣誉时刻推导）
    result = parse_and_store(api_data, heat_data)
    return 0 if result else 1


if __name__ == "__main__":
    raise SystemExit(main())
