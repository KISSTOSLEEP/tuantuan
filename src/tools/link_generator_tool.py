"""链接生成工具 - 生成游戏组队、音乐直达、社交平台可点击链接"""
import os
import json
from langchain.tools import tool


# ======== 游戏平台链接配置 ========
GAME_PLATFORMS = {
    "王者荣耀": {
        "name": "王者荣耀",
        "type": "mobile",
        "official_url": "https://pvp.qq.com",
        "invite_guide": "游戏内创建房间 → 复制房间号 → 分享给好友",
        "search_url": "https://pvp.qq.com/web201605/search.shtml?kw=",
        "app_deeplink": "wegame://pvp.qq",
        "tips": "创建房间后点「分享」生成邀请链接，好友点击秒进房间",
    },
    "无畏契约": {
        "name": "无畏契约（瓦罗兰特）",
        "type": "pc",
        "official_url": "https://val.qq.com",
        "invite_guide": "游戏内生成房间代码 → 选择分享 → 复制跨端邀请链接",
        "search_url": "https://val.qq.com/act/",
        "tips": "PC端生成链接后可直接分享到微信，好友点链接一键进房",
    },
    "Steam": {
        "name": "Steam",
        "type": "pc",
        "official_url": "https://store.steampowered.com",
        "invite_guide": "Steam好友列表 → 右键好友 → 邀请加入游戏，或创建大厅分享链接",
        "search_url": "https://store.steampowered.com/search/?term=",
        "tips": "打开Steam → 好友列表 → 右键「邀请加入游戏」，或者创建房间后Shift+Tab呼出Steam界面邀请",
    },
    "英雄联盟": {
        "name": "英雄联盟（LOL）",
        "type": "pc",
        "official_url": "https://lol.qq.com",
        "invite_guide": "游戏客户端内 → 好友列表 → 邀请组队，或创建房间分享房间号",
        "search_url": "https://lol.qq.com/act/",
        "tips": "客户端内好友列表右键邀请，或者开自定义房间分享房间名",
    },
    "原神": {
        "name": "原神",
        "type": "multi",
        "official_url": "https://ys.mihoyo.com",
        "invite_guide": "游戏内联机系统 → 输入好友UID或直接邀请在线好友进入世界",
        "search_url": "https://www.miyoushe.com/ys/",
        "tips": "按U键打开联机页面，输入好友UID就能串门了",
    },
    "蛋仔派对": {
        "name": "蛋仔派对",
        "type": "mobile",
        "official_url": "https://danzai.163.com",
        "invite_guide": "游戏内组队 → 生成邀请链接分享给好友",
        "search_url": "https://danzai.163.com",
        "tips": "创建房间后点分享生成链接，好友点击直接进房间一起玩",
    },
    "腾讯会议": {
        "name": "腾讯会议（线上一起玩）",
        "type": "multi",
        "official_url": "https://meeting.tencent.com",
        "invite_guide": "创建会议 → 复制会议号和链接 → 分享给好友",
        "search_url": "https://meeting.tencent.com",
        "tips": "适合线上一起看电影、听歌、唠嗑，比游戏门槛低",
    },
    "Discord": {
        "name": "Discord（国外常用语音）",
        "type": "pc",
        "official_url": "https://discord.com",
        "invite_guide": "创建服务器 → 生成邀请链接 → 分享给好友",
        "search_url": "https://discord.com/channels/",
        "tips": "国内用的话推荐开黑啦（Kaiheila）替代",
    },
}

# ======== 音乐平台链接配置 ========
MUSIC_PLATFORMS = {
    "网易云音乐": {
        "name": "网易云音乐",
        "search_url": "https://music.163.com/#/search?q=",
        "share_song_guide": "打开歌曲 → 右上角··· → 分享 → 复制链接",
        "share_playlist_guide": "打开歌单 → 右上角··· → 分享 → 复制链接",
        "download_url": "https://music.163.com",
    },
    "QQ音乐": {
        "name": "QQ音乐",
        "search_url": "https://y.qq.com/n/ryqq/search?w=",
        "share_song_guide": "打开歌曲 → 右上角··· → 分享 → 复制链接",
        "share_playlist_guide": "打开歌单 → 右上角··· → 分享 → 复制链接",
        "download_url": "https://y.qq.com",
    },
    "B站": {
        "name": "哔哩哔哩（B站音乐）",
        "search_url": "https://search.bilibili.com/all?keyword=",
        "share_song_guide": "打开视频 → 分享 → 复制链接",
        "share_playlist_guide": "收藏夹 → 分享收藏夹",
        "download_url": "https://www.bilibili.com",
    },
    "Spotify": {
        "name": "Spotify（国外）",
        "search_url": "https://open.spotify.com/search/",
        "share_song_guide": "打开歌曲 → 右键/长按 → 分享 → 复制链接",
        "share_playlist_guide": "打开歌单 → 右键/长按 → 分享 → 复制链接",
        "download_url": "https://open.spotify.com",
    },
    "抖音": {
        "name": "抖音音乐",
        "search_url": "https://www.douyin.com/search/",
        "share_song_guide": "打开音乐视频 → 分享 → 复制链接",
        "share_playlist_guide": "收藏音乐 → 分享歌单",
        "download_url": "https://www.douyin.com",
    },
}

# ======== 社交约玩平台 ========
SOCIAL_PLATFORMS = {
    "微信": {
        "guide": "建个微信群 → 把想约的人拉进来 → 在群里敲定时间地点",
        "tips": "微信群里可以发位置共享、群公告定时间、群接龙统计人数",
    },
    "QQ": {
        "guide": "建个QQ群或讨论组 → 用群公告发活动详情 → QQ语音开黑更方便",
        "tips": "QQ有游戏中心可以直接拉人打游戏，支持屏幕共享一起看剧",
    },
    "线下约见": {
        "guide": "选一个公共商圈 → 确定时间 → 发定位给对方",
        "suggestions": [
            "奶茶店（一点点、喜茶、霸王茶姬）",
            "KFC/麦当劳（不贵、不限时）",
            "商场内的电玩城/抓娃娃机",
            "猫咖/狗咖（自带话题）",
            "公园（免费，适合散步聊天）",
        ],
        "safety": "第一次见面一定选公共场所！告知朋友你的行踪",
    },
}


def _game_invite_link(game_name, platform="mobile"):
    """生成游戏组队链接"""
    game = GAME_PLATFORMS.get(game_name)
    if not game:
        return f"没找到 {game_name} 的信息，你可以直接告诉对方你想玩什么游戏"
    
    return (
        f"🎮 **{game['name']}**\n"
        f"🔗 官网：{game['official_url']}\n"
        f"📝 怎么组队：{game['invite_guide']}\n"
        f"💡 小技巧：{game['tips']}\n"
    )


def _music_search_link(emotion_or_style, platform="网易云音乐"):
    """生成音乐搜索直达链接"""
    platform_info = MUSIC_PLATFORMS.get(platform, MUSIC_PLATFORMS["网易云音乐"])
    
    # 构造搜索关键词
    keyword_map = {
        "depressed": "治愈 温暖 轻快 纯音乐",
        "sad": "治愈 温暖 纯音乐",
        "anxious": "白噪音 冥想 放松 雨声",
        "anxiety": "白噪音 冥想 放松 雨声",
        "angry": "舒缓 抒情 慢歌 calm",
        "mad": "舒缓 抒情 轻音乐",
        "manic": "舒缓 抒情 calm down",
        "happy": "开心 欢快 节奏",
        "bored": "有趣 轻快 惊喜歌单",
        "lonely": "温暖 陪伴 治愈",
        "tired": "放松 舒缓 纯音乐 休息",
        "失落": "治愈 温暖 轻快",
        "emo": "emo 治愈 温暖",
        "烦躁": "白噪音 冥想 放松",
        "失眠": "失眠 助眠 白噪音 轻音乐",
        "焦虑": "放松 冥想 白噪音",
        "低落": "治愈 温暖 轻快 纯音乐",
        "生气": "舒缓 calm down 慢歌",
        "开心": "欢快 开心 节奏感",
        "无聊": "有趣 惊喜 宝藏歌单",
        "孤独": "温暖 陪伴 治愈",
        "累": "放松 休息 纯音乐",
    }
    
    keyword = keyword_map.get(emotion_or_style.lower(), emotion_or_style)
    encoded_keyword = keyword.replace(" ", "%20")
    search_url = platform_info["search_url"] + encoded_keyword
    
    return (
        f"🎵 **{platform_info['name']}** 搜索「{keyword}」\n"
        f"🔗 直达链接：{search_url}\n"
        f"📝 分享歌曲：{platform_info['share_song_guide']}\n"
        f"📝 分享歌单：{platform_info['share_playlist_guide']}\n"
    )


@tool
def generate_game_link(game_name: str) -> str:
    """生成游戏组队链接和邀请方式。对方想打游戏时，告诉TA怎么创建房间、生成邀请链接分享给搭子。
    支持：王者荣耀、无畏契约（瓦罗兰特）、Steam、英雄联盟、原神、蛋仔派对等。
    """
    return _game_invite_link(game_name)


@tool
def generate_music_link(emotion_or_keyword: str, platform: str = "网易云音乐") -> str:
    """根据情绪或心情关键词，生成音乐平台搜索直达链接。对方想听歌时调用。
    emotion_or_keyword: 情绪关键词（如：低落、焦虑、烦躁、失眠、开心、无聊、emo、孤独、累等）
    platform: 音乐平台（网易云音乐、QQ音乐、B站、Spotify、抖音）
    """
    return _music_search_link(emotion_or_keyword, platform)


@tool
def generate_meetup_guide(activity: str = "随便逛逛", city: str = "") -> str:
    """生成线下约见地点建议和安全提醒。匹配到搭子后，告诉TA可以约在哪里、怎么碰面。
    activity: 想做的活动（吃饭/喝奶茶/逛街/看电影/打游戏/散步/唱歌）
    city: 城市名（可选）
    """
    city_str = f"📍 **城市**：{city}\n" if city else ""
    
    venue_map = {
        "吃饭": "商圈里的热门餐厅、美食广场",
        "喝奶茶": "一点点、喜茶、霸王茶姬、蜜雪冰城",
        "逛街": "大型商场、步行街",
        "看电影": "商圈电影院（看完还能顺便吃饭）",
        "打游戏": "网咖、电竞馆、游戏厅",
        "散步": "公园、江边、校园",
        "唱歌": "KTV、迷你ktv亭",
        "默认": "商场/KFC/麦当劳/奶茶店",
    }
    venue = venue_map.get(activity, venue_map["默认"])
    
    return (
        f"📅 **约见指南**\n"
        f"{city_str}"
        f"🎯 活动：{activity}\n"
        f"📍 推荐地点：{venue}\n\n"
        f"📝 碰面步骤：\n"
        f"1. 商量好时间地点\n"
        f"2. 互相发个定位\n"
        f"3. 到了先发消息确认\n\n"
        f"🌱 **安全提醒**：\n"
        f"- 第一次见面选公共场所\n"
        f"- 告诉一个朋友你的去向\n"
        f"- 感觉不舒服随时走，不用解释\n"
        f"- 手机保持电量充足 📱\n"
    )


@tool
def generate_voice_chat_link(platform: str = "微信") -> str:
    """生成语音/视频聊天连接方式。对方想线上一起玩、一起听歌、一起看电影时调用。
    platform: 语音平台（微信、QQ、腾讯会议、Discord）
    """
    platform_configs = {
        "微信": {
            "guide": "微信语音/视频通话：打开微信 → 选择好友 → 点「+」→ 语音通话/视频通话",
            "multi": "微信群语音：进入群聊 → 点「+」→ 选择「语音通话」→ 勾选要呼叫的人",
            "tips": "微信群语音最多支持9人，适合小型聚会",
        },
        "QQ": {
            "guide": "QQ语音通话：打开好友聊天 → 点电话图标 → 语音通话",
            "multi": "QQ群语音/屏幕共享：进入群聊 → 点电话图标 → 选择语音通话 → 可开启屏幕共享一起看剧",
            "tips": "QQ支持屏幕共享，可以一起看电影",
        },
        "腾讯会议": {
            "guide": "腾讯会议：App → 快速会议 → 复制会议号分享给好友",
            "multi": "支持屏幕共享、多人视频、录制回放",
            "tips": "适合线上一起看剧/看电影/听歌，可以开摄像头更有氛围",
            "download": "https://meeting.tencent.com",
        },
        "Discord": {
            "guide": "Discord：创建服务器 → 创建语音频道 → 邀请好友加入",
            "multi": "支持多人语音、屏幕共享、聊天频道分离",
            "tips": "国内也可以使用「开黑啦」替代",
            "download": "https://discord.com",
        },
    }
    
    config = platform_configs.get(platform, platform_configs["微信"])
    dl_link = f"\n🔗 下载：{config.get('download', '')}" if config.get('download') else ""
    
    return (
        f"🔊 **{platform}线上连接**\n"
        f"📝 连线方式：{config['guide']}\n"
        f"👥 多人模式：{config['multi']}\n"
        f"💡 小贴士：{config['tips']}"
        f"{dl_link}\n"
    )