"""
紧急联系人管理工具 —— 保存和查询用户的紧急联系人信息
"""
import os
import json
from typing import Optional
from langchain.tools import tool

# 联系人数据文件路径
CONTACTS_FILE = os.path.join(
    os.getenv("COZE_WORKSPACE_PATH", "/workspace/projects"),
    "assets/emergency_contacts.json"
)


def _load_contacts() -> dict:
    """加载联系人数据"""
    try:
        if os.path.exists(CONTACTS_FILE):
            with open(CONTACTS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        pass
    return {"contacts": []}


def _save_contacts(data: dict):
    """保存联系人数据"""
    with open(CONTACTS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


@tool
def save_emergency_contact(name: str, phone: str, relationship: str = "") -> str:
    """保存紧急联系人信息。
    
    当用户想设置紧急联系人时调用此工具。
    
    Args:
        name: 联系人姓名
        phone: 联系电话
        relationship: 与用户的关系（如家人、朋友等），可选

    Returns:
        保存结果确认
    """
    data = _load_contacts()
    
    # 检查是否已存在
    for contact in data["contacts"]:
        if contact["name"] == name and contact["phone"] == phone:
            return f"📋 {name}（{phone}）已经是你的紧急联系人啦~"
    
    contact = {
        "name": name,
        "phone": phone,
        "relationship": relationship
    }
    data["contacts"].append(contact)
    _save_contacts(data)
    
    rel_text = f"（{relationship}）" if relationship else ""
    return (
        f"✅ 已保存紧急联系人！\n\n"
        f"姓名：{name} {rel_text}\n"
        f"电话：{phone}\n\n"
        f"万一有需要的时候，记得可以联系TA哦 🧡"
    )


@tool
def get_emergency_contacts() -> str:
    """查询已保存的紧急联系人列表。
    
    当用户想知道自己的紧急联系人有谁时调用。

    Returns:
        联系人列表
    """
    data = _load_contacts()
    
    if not data["contacts"]:
        return (
            "📭 你还没有设置紧急联系人呢~\n\n"
            "要不要现在设置一个？告诉我TA的名字和电话就好~\n"
            "可以是家人、朋友，或者任何一个你信任的人 🧡"
        )
    
    result = "📋 你的紧急联系人：\n\n"
    for i, contact in enumerate(data["contacts"], 1):
        rel_text = f"（{contact['relationship']}）" if contact.get("relationship") else ""
        result += f"{i}. {contact['name']} {rel_text}\n"
        result += f"   📞 {contact['phone']}\n\n"
    
    result += "需要联系TA们的时候，不要犹豫 🧡"
    return result


@tool
def delete_emergency_contact(name: str, phone: Optional[str] = "") -> str:
    """删除紧急联系人。

    Args:
        name: 要删除的联系人姓名
        phone: 联系电话（可选，用于精确匹配）

    Returns:
        删除结果
    """
    data = _load_contacts()
    original_count = len(data["contacts"])
    
    if phone:
        data["contacts"] = [
            c for c in data["contacts"]
            if not (c["name"] == name and c["phone"] == phone)
        ]
    else:
        data["contacts"] = [
            c for c in data["contacts"]
            if c["name"] != name
        ]
    
    if len(data["contacts"]) < original_count:
        _save_contacts(data)
        return f"✅ 已删除联系人 {name}"
    else:
        return f"❌ 没有找到叫 {name} 的联系人"