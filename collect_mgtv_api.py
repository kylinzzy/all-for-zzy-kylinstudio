#!/usr/bin/env python3
"""
密室大逃脱第8季 - 芒果TV官方API全自动采集脚本 (v3 - API直连版)

★ 核心突破：找到了芒果TV内部API，可一次性获取全部集数的实时播放量
   API: https://mobile-thor.api.mgtv.com/v1/vod/info?clipId=887305
   字段: data.template.modules[].list[].subTitle = "7541.2万次播放"

无需Cookie、无需签名、无需浏览器渲染。

用法：
  python3 collect_mgtv_api.py collect      # 采集并更新 episode_data.json
  python3 collect_mgtv_api.py preview      # 仅预览API返回，不写入
"""

import json
import re
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
DATA_FILE = BASE_DIR / "episode_data.json"

CLIP_ID = "887305"
API_URL = f"https://mobile-thor.api.mgtv.com/v1/vod/info?clipId={CLIP_ID}"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36"


def fetch_api():
    """调用芒果TV thor API获取全量数据"""
    req = urllib.request.Request(
        API_URL,
        headers={
            "User-Agent": UA,
            "Referer": "https://www.mgtv.com/",
            "Accept": "application/json, text/plain, */*",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def parse_playcount(text):
    """将 '7541.2万次播放' / '2.1亿次播放' 转换为万为单位的数字"""
    if not text:
        return None
    m = re.match(r"([\d.]+)\s*([万亿])次播放", text)
    if not m:
        return None
    num = float(m.group(1))
    unit = m.group(2)
    return num * 10000 if unit == "亿" else num


def extract_episodes(api_data):
    """递归提取所有含 subTitle 播放量的视频条目"""
    results = []
    seen = set()

    def walk(obj):
        if isinstance(obj, list):
            for item in obj:
                walk(item)
            return
        if not isinstance(obj, dict):
            return
        # 判断是否是视频条目
        vid = obj.get("videoId")
        sub = obj.get("subTitle", "")
        if vid and isinstance(sub, str) and "次播放" in sub and vid not in seen:
            seen.add(vid)
            results.append({
                "video_id": str(vid),
                "title": obj.get("title", ""),
                "playcount_text": sub,
                "playcount_wan": parse_playcount(sub),
                "release_date": obj.get("rbTitle", ""),
                "serialno": obj.get("serialno", ""),
                "vip": bool(obj.get("vipMark")),
            })
        for v in obj.values():
            walk(v)

    walk(api_data)
    # 按 serialno 排序
    results.sort(key=lambda x: int(x["serialno"]) if str(x["serialno"]).isdigit() else 999)
    return results


def load_data():
    if DATA_FILE.exists():
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"metadata": {}, "episodes": {}, "milestones": {}, "platform_summary": {}}


def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def check_milestone_crossing(old_wan, new_wan):
    """检测是否跨越了5000万整数倍节点，返回跨越的节点列表"""
    if old_wan is None or new_wan is None or new_wan <= old_wan:
        return []
    NODE = 5000  # 5000万
    old_level = int(old_wan // NODE)
    new_level = int(new_wan // NODE)
    return [(i + 1) * NODE for i in range(old_level, new_level)]


def collect(write=True):
    print("=" * 74)
    print("密室大逃脱第8季 - 芒果TV官方API采集")
    print(f"API: {API_URL}")
    print("=" * 74)

    api_json = fetch_api()
    if api_json.get("code") != 200:
        print(f"[ERROR] API返回异常: code={api_json.get('code')} msg={api_json.get('msg')}")
        return 1

    episodes = extract_episodes(api_json.get("data", {}))
    now = datetime.now()
    now_str = now.strftime("%Y-%m-%dT%H:%M:%S")

    print(f"\n采集时间: {now_str}")
    print(f"采集到 {len(episodes)} 集\n")
    print(f"{'序':<4}{'集名':<34}{'播放量':<14}{'上线日期':<12}")
    print("-" * 74)
    for ep in episodes:
        title = ep["title"][:32]
        print(f"{ep['serialno']:<4}{title:<34}{ep['playcount_text']:<14}{ep['release_date']:<12}")

    if not write:
        print("\n[preview模式] 未写入数据文件")
        return 0

    # 写入 episode_data.json
    data = load_data()
    data.setdefault("episodes", {})
    data.setdefault("milestones", {})
    data.setdefault("metadata", {})

    new_milestones = []
    updated = 0

    for ep in episodes:
        vid = ep["video_id"]
        node = data["episodes"].get(vid, {})
        old_wan = node.get("current_playcount_wan")
        new_wan = ep["playcount_wan"]

        # 检测里程碑跨越（仅当有历史值时）
        if old_wan is not None:
            crossed = check_milestone_crossing(old_wan, new_wan)
            for node_wan in crossed:
                ms_list = data["milestones"].setdefault(vid, [])
                # 避免重复
                if not any(m["node_wan"] == node_wan for m in ms_list):
                    ms_list.append({
                        "node_wan": node_wan,
                        "node_yi": f"{node_wan/10000:.1f}",
                        "status": "confirmed",
                        "achieve_time": now_str,
                        "achieve_source": f"API采集检测到跨越（{old_wan:.1f}万 -> {new_wan:.1f}万）",
                        "detected_at": now_str,
                    })
                    new_milestones.append((ep["title"], node_wan))

        # 更新集数数据
        node.update({
            "name": node.get("name") or ep["title"],
            "title": ep["title"],
            "video_id": vid,
            "serialno": ep["serialno"],
            "launch": ep["release_date"],
            "vip": ep["vip"],
            "current_playcount_wan": new_wan,
            "current_playcount_text": ep["playcount_text"],
            "last_collect_time": now_str,
            "data_note": "",
        })
        hist = node.setdefault("collection_history", [])
        # 只在数值变化时追加历史（避免冗余）
        if not hist or hist[-1].get("playcount_wan") != new_wan:
            hist.append({
                "time": now_str,
                "playcount_wan": new_wan,
                "playcount_text": ep["playcount_text"],
                "source_url": API_URL,
                "source_note": "芒果TV官方API (mobile-thor v1/vod/info)",
            })
            updated += 1
        data["episodes"][vid] = node

    data["metadata"]["last_collect_time"] = now_str
    data["metadata"]["total_collections"] = data["metadata"].get("total_collections", 0) + 1
    data["metadata"]["collect_method"] = "芒果TV官方API直连 (mobile-thor)"
    data["metadata"]["api_url"] = API_URL
    data["metadata"]["episode_count"] = len(episodes)

    save_data(data)

    total_wan = sum(e["playcount_wan"] for e in episodes if e["playcount_wan"])
    print("-" * 74)
    print(f"全站合计: {total_wan/10000:.2f}亿 ({total_wan:,.1f}万)")
    print(f"\n[写入完成] {updated} 集数值有变化 | 累计采集 {data['metadata']['total_collections']} 次")

    if new_milestones:
        print(f"\n★★★ 新达成 {len(new_milestones)} 个里程碑节点！")
        for title, node_wan in new_milestones:
            print(f"    {title} -> {node_wan/10000:.1f}亿")
    return 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "collect"
    sys.exit(collect(write=(cmd != "preview")))
