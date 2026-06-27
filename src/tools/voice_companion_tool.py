"""语音陪伴工具 - TTS"""
import os
import requests
from langchain.tools import tool
from coze_coding_utils.log.write_log import request_context
from coze_coding_utils.runtime_ctx.context import new_context

@tool
def voice_companion(message: str, voice_style: str = "温暖") -> str:
    """把你想对用户说的话转成语音发过去。
    message: 要转成语音的文字内容（用口语化的短句，不要太长）
    voice_style: 语音风格，可选 温暖/温柔/鼓励/朋友
    """
    ctx = request_context.get() or new_context(method="voice.companion")
    
    try:
        from coze_coding_dev_sdk import TTSClient
        client = TTSClient(ctx=ctx)
        
        # Voice mapping
        voice_map = {
            "温暖": "zh_female_xiaohe_uranus_bigtts",
            "温柔": "zh_female_vv_uranus_bigtts",
            "鼓励": "zh_female_jitangnv_saturn_bigtts",
            "朋友": "zh_female_meilinvyou_saturn_bigtts",
            "男生": "zh_male_m191_uranus_bigtts",
            "可爱": "saturn_zh_female_keainvsheng_tob",
        }
        speaker = voice_map.get(voice_style, "zh_female_xiaohe_uranus_bigtts")
        
        # Speed adjustment based on style
        speech_rate = -10 if voice_style in ["温暖", "温柔"] else 0
        
        audio_url, audio_size = client.synthesize(
            uid="user_companion",
            text=message,
            speaker=speaker,
            speech_rate=speech_rate,
            audio_format="mp3"
        )
        
        return f"🎤 语音消息已生成：\n{audio_url}\n（点击即可播放，有效期24小时）\n💬 文字版：{message}"
        
    except Exception as e:
        return f"语音生成暂时不可用。不过话还是要说给你听：{message}"
