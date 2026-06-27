"""音乐推荐工具 - 情绪+时间段双维度推荐 + 搜索可播放链接"""

import json
import logging
import os
import random
from typing import Optional

from langchain.tools import tool

from coze_coding_utils.log.write_log import request_context
from coze_coding_utils.runtime_ctx.context import new_context

logger = logging.getLogger(__name__)

# ========== 音乐曲库 ==========

# 按情绪分类
MOOD_PLAYLISTS = {
    "emo": {
        "label": "😢 一个人待着",
        "songs": [
            ("晚风", "陈婧霏"),
            ("走马", "陈粒"),
            ("山海", "草东没有派对"),
            ("越过山丘", "李宗盛"),
            ("平凡之路", "朴树"),
            ("后来的我们", "五月天"),
            ("安和桥", "宋冬野"),
            ("成都", "赵雷"),
            ("南山南", "马頔"),
            ("理想三旬", "陈鸿宇"),
            ("一生所爱", "卢冠廷"),
            ("那些花儿", "朴树"),
            ("白月光与朱砂痣", "大籽"),
            ("晚婚", "李宗盛"),
            ("像我这样的人", "毛不易"),
            ("消愁", "毛不易"),
            ("借我", "谢春花"),
            ("儿时", "刘昊霖"),
            ("父亲写的散文诗", "许飞"),
            ("路过人间", "郁可唯"),
        ],
    },
    "angry": {
        "label": "🔥 想发泄",
        "songs": [
            ("逆战", "张杰"),
            ("我相信", "杨培安"),
            ("夜曲", "周杰伦"),
            ("霍元甲", "周杰伦"),
            ("双截棍", "周杰伦"),
            ("倔强", "五月天"),
            ("离开地球表面", "五月天"),
            ("Yellow", "Coldplay"),
            ("In the End", "Linkin Park"),
            ("Numb", "Linkin Park"),
            ("Uprising", "Muse"),
            ("Centuries", "Fall Out Boy"),
            ("Believer", "Imagine Dragons"),
            ("Thunder", "Imagine Dragons"),
            ("We Will Rock You", "Queen"),
            ("追梦赤子心", "GALA"),
            ("海阔天空", "Beyond"),
            ("曾经的你", "许巍"),
            ("蓝莲花", "许巍"),
            ("生如夏花", "朴树"),
        ],
    },
    "anxious": {
        "label": "😰 焦虑不安",
        "songs": [
            ("River Flows In You", "Yiruma"),
            ("Kiss The Rain", "Yiruma"),
            ("A Little Story", "Valentin"),
            ("春よ、来い", "松任谷由实"),
            ("月光", "德彪西"),
            ("G弦上的咏叹调", "巴赫"),
            ("Canon in D", "Pachelbel"),
            ("Weightless", "Marconi Union"),
            ("Clair de Lune", "Debussy"),
            ("雨滴", "久石让"),
            ("Summer", "久石让"),
            ("菊次郎的夏天", "久石让"),
            ("天空之城", "久石让"),
            ("风之诗", "押尾光太郎"),
            ("Like A Star", "Youngso Kim"),
            ("花之舞", "Dj Okawari"),
            ("变得更好", "V.A."),
            ("告白的夜", "Various Artists"),
            ("Eutopia", "Yoohsic Roomz"),
            ("星河", "Various Artists"),
        ],
    },
    "happy": {
        "label": "🎉 心情不错",
        "songs": [
            ("阳光宅男", "周杰伦"),
            ("园游会", "周杰伦"),
            ("简单爱", "周杰伦"),
            ("七里香", "周杰伦"),
            ("恋爱ing", "五月天"),
            ("干杯", "五月天"),
            ("伤心的人别听慢歌", "五月天"),
            ("好运来", "祖海"),
            ("恭喜发财", "刘德华"),
            ("小苹果", "筷子兄弟"),
            ("最炫民族风", "凤凰传奇"),
            ("月亮之上", "凤凰传奇"),
            ("快乐崇拜", "潘玮柏/张韶涵"),
            ("第一天", "孙燕姿"),
            ("舞娘", "蔡依林"),
            ("日不落", "蔡依林"),
            ("达尔文", "蔡健雅"),
            ("红色高跟鞋", "蔡健雅"),
            ("爱你", "王心凌"),
            ("Honey", "王心凌"),
            ("你要跳舞吗", "新裤子"),
            ("霓虹甜心", "马赛克"),
            ("别再问我什么是迪斯科", "张蔷"),
            ("爱情万岁", "郑秀文"),
            ("眉飞色舞", "郑秀文"),
        ],
    },
    "tired": {
        "label": "😴 累了歇会儿",
        "songs": [
            ("明日", "陈粒"),
            ("宝贝", "张悬"),
            ("小半", "陈粒"),
            ("寻", "华晨宇"),
            ("好想好想你", "邓紫棋"),
            ("光年之外", "邓紫棋"),
            ("起风了", "买辣椒也用券"),
            ("小幸运", "田馥甄"),
            ("追光者", "岑宁儿"),
            ("一次就好", "杨宗纬"),
            ("当你老了", "赵照"),
            ("时间都去哪儿了", "王铮亮"),
            ("假如爱有天意", "李健"),
            ("贝加尔湖畔", "李健"),
            ("车站", "李健"),
            ("异乡人", "李健"),
            ("风吹麦浪", "李健"),
            ("女儿情", "吴静"),
            ("大话西游", "卢冠廷"),
            ("一生所爱", "卢冠廷"),
        ],
    },
}

# 按时间段推荐（新增维度）
TIME_MOOD_MAP = {
    "morning": {"label": "🌅 早上起床", "moods": ["happy", "tired"]},
    "afternoon": {"label": "☀️ 午后时光", "moods": ["happy", "anxious", "tired"]},
    "evening": {"label": "🌆 傍晚时分", "moods": ["emo", "happy", "tired"]},
    "night": {"label": "🌙 夜深了", "moods": ["emo", "anxious", "tired"]},
    "late_night": {"label": "🌃 凌晨了", "moods": ["emo", "anxious", "tired"]},
}


def _get_current_time_period() -> str:
    """根据当前时间判断时间段"""
    hour = int(os.environ.get("CURRENT_HOUR", "0"))
    if hour == 0:
        from datetime import datetime
        hour = datetime.now().hour
    if 5 <= hour < 12:
        return "morning"
    elif 12 <= hour < 17:
        return "afternoon"
    elif 17 <= hour < 22:
        return "evening"
    elif 22 <= hour < 24:
        return "night"
    else:
        return "late_night"


@tool
def recommend_music(mood: str = "", count: int = 5) -> str:
    """根据当前情绪状态推荐音乐，情绪和推荐描述会结合当前时间段。

    Args:
        mood: 情绪状态，可选值：emo（低落）、angry（愤怒）、anxious（焦虑）、happy（开心）、tired（疲惫）。空字符串则自动判断
        count: 推荐歌曲数量，默认5首，最多10首

    Returns:
        推荐歌曲清单和播放指引
    """
    count = min(10, max(3, count))
    time_period = _get_current_time_period()

    # 如果没有指定情绪，按时间段推荐
    if not mood or mood not in MOOD_PLAYLISTS:
        time_info = TIME_MOOD_MAP.get(time_period, TIME_MOOD_MAP["night"])
        mood_options = time_info["moods"]
        # 随机选择一个
        mood = random.choice(mood_options)

    playlist = MOOD_PLAYLISTS.get(mood)
    if not playlist:
        mood = "emo"
        playlist = MOOD_PLAYLISTS["emo"]

    # 随机选取歌曲
    selected = random.sample(playlist["songs"], min(count, len(playlist["songs"])))

    time_info = TIME_MOOD_MAP.get(time_period, TIME_MOOD_MAP["night"])

    lines = [
        f"🎵 {playlist['label']} · {time_info['label']}",
        "",
    ]

    for i, (song, artist) in enumerate(selected, 1):
        lines.append(f"  {i}. 《{song}》- {artist}")

    lines.extend([
        "",
        "🔗 【去听完整版】",
        "   复制歌名到以下平台搜索：",
        "   · 网易云音乐 → music.163.com",
        "   · QQ音乐 → y.qq.com",
        "   · B站搜 → bilibili.com",
        "   · Spotify → open.spotify.com",
        "",
        "💡 输入你想听的歌名，我可以帮你找到播放链接！",
    ])

    return "\n".join(lines)


@tool
def search_song_url(song_name: str, artist: str = "", platform: str = "netease") -> str:
    """搜索指定歌曲的播放链接

    Args:
        song_name: 歌曲名称
        artist: 歌手名称（可选），提供可提高搜索准确度
        platform: 目标平台，可选值：netease（网易云）、qqmusic（QQ音乐）、bilibili（B站）、spotify（Spotify）

    Returns:
        搜索到的歌曲链接
    """
    if not song_name:
        return "❌ 请输入歌曲名称"

    try:
        from coze_coding_dev_sdk import SearchClient
        ctx = request_context.get() or new_context(method="search_music")
        client = SearchClient(ctx=ctx)

        query = f"{song_name}"
        if artist:
            query += f" {artist}"

        platform_names = {
            "netease": "网易云音乐",
            "qqmusic": "QQ音乐",
            "bilibili": "B站",
            "spotify": "Spotify",
        }
        platform_name = platform_names.get(platform, "网易云音乐")
        query += f" {platform_name}"

        response = client.web_search(query=query, count=5)

        results = []
        if response and response.web_items:
            for item in response.web_items[:5]:
                title = item.title or ""
                snippet = item.snippet or ""
                url = item.url or ""
                results.append(f"  · {title}\n    {url}\n    {snippet[:80]}")

        if results:
            artist_info = f" ({artist})" if artist else ""
            return (
                f"🎵 搜索结果：{song_name}{artist_info}\n"
                f"   平台：{platform_name}\n\n"
                + "\n".join(results[:3])
            )
        else:
            return f"没有找到 {song_name} 的播放链接，换个平台试试？"

    except Exception as e:
        logger.error(f"搜索歌曲失败: {e}")
        return f"搜索失败，你可以直接去网易云音乐搜索《{song_name}》试试~"


# 为保持兼容性保留旧接口名
music_recommend = recommend_music