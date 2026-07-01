"""DeepSeek 对话插件 - 管理类（白名单/黑名单/统计/封禁词/人设/会话/配额/Token）"""
import json
import os
from datetime import datetime, date
from typing import Dict, List, Set, Optional
from nonebot import logger

from . import config as aichat_config
from .config import (
    CONFIG, WHITELIST_FILE, BLACKLIST_FILE, STATS_FILE,
    BANWORDS_FILE, PERSONA_FILE, TOKEN_DAILY_FILE, SPLIT_STATE_FILE,
)


class WhitelistManager:
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.whitelist: Set[str] = set()
        self.load()

    def load(self):
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        self.whitelist = set(map(str, data))
            except Exception as e:
                logger.error(f"加载白名单失败：{e}")

    def save(self):
        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(list(self.whitelist), f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存白名单失败：{e}")

    def add(self, user_id: str): self.whitelist.add(user_id); self.save()
    def remove(self, user_id: str):
        if user_id in self.whitelist: self.whitelist.remove(user_id); self.save()
    def contains(self, user_id: str) -> bool: return user_id in self.whitelist
    def list_all(self) -> List[str]: return list(self.whitelist)


class BlacklistManager:
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.blacklist_users: Set[str] = set()
        self.blacklist_groups: Set[str] = set()
        self.load()

    def load(self):
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.blacklist_users = set(map(str, data.get("users", [])))
                    self.blacklist_groups = set(map(str, data.get("groups", [])))
            except Exception as e:
                logger.error(f"加载黑名单失败：{e}")

    def save(self):
        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump({"users": list(self.blacklist_users), "groups": list(self.blacklist_groups)},
                          f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存黑名单失败：{e}")

    def add_user(self, uid: str): self.blacklist_users.add(uid); self.save()
    def remove_user(self, uid: str):
        if uid in self.blacklist_users: self.blacklist_users.remove(uid); self.save()
    def add_group(self, gid: str): self.blacklist_groups.add(gid); self.save()
    def remove_group(self, gid: str):
        if gid in self.blacklist_groups: self.blacklist_groups.remove(gid); self.save()
    def is_user_blacklisted(self, uid: str) -> bool: return uid in self.blacklist_users
    def is_group_blacklisted(self, gid: str) -> bool: return gid in self.blacklist_groups
    def list_all_users(self) -> List[str]: return list(self.blacklist_users)
    def list_all_groups(self) -> List[str]: return list(self.blacklist_groups)


class StatsManager:
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.data = {"total_calls": 0, "today_calls": 0, "last_date": str(date.today())}
        self.load()

    def load(self):
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self.data = data
                        if self.data.get("last_date") != str(date.today()):
                            self.data["today_calls"] = 0
                            self.data["last_date"] = str(date.today())
                            self.save()
            except Exception as e:
                logger.error(f"加载统计数据失败：{e}")

    def save(self):
        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存统计数据失败：{e}")

    def update(self):
        today_str = str(date.today())
        if self.data.get("last_date") != today_str:
            self.data["today_calls"] = 0; self.data["last_date"] = today_str
        self.data["total_calls"] = self.data.get("total_calls", 0) + 1
        self.data["today_calls"] = self.data.get("today_calls", 0) + 1
        self.save()

    def get_stats(self):
        return {"total_calls": self.data.get("total_calls", 0),
                "today_calls": self.data.get("today_calls", 0),
                "last_date": self.data.get("last_date", str(date.today()))}


class BanwordsManager:
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.banwords: Set[str] = set()
        self.load()

    def load(self):
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list): self.banwords = set(data)
            except Exception as e:
                logger.error(f"加载封禁词失败：{e}")

    def save(self):
        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(list(self.banwords), f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存封禁词失败：{e}")

    def add(self, word: str): self.banwords.add(word); self.save()
    def remove(self, word: str):
        if word in self.banwords: self.banwords.remove(word); self.save()
    def contains(self, text: str) -> bool: return any(w in text for w in self.banwords)
    def list_all(self) -> List[str]: return list(self.banwords)


class TokenDailyManager:
    """每日 Token 用量持久化"""
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.data: Dict[str, Dict[str, int]] = {}
        self.load()
        if not os.path.exists(self.file_path):
            self.save()

    def load(self):
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
            except Exception:
                self.data = {}

    def save(self):
        keys = sorted(self.data.keys(), reverse=True)[:60]
        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump({k: self.data[k] for k in keys}, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存Token统计失败：{e}")

    def add(self, input_tokens: int, output_tokens: int):
        today_str = str(date.today())
        if today_str not in self.data:
            self.data[today_str] = {"input": 0, "output": 0, "calls": 0}
        self.data[today_str]["input"] += input_tokens
        self.data[today_str]["output"] += output_tokens
        self.data[today_str]["calls"] = self.data[today_str].get("calls", 0) + 1
        self.save()


class PersonaManager:
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.user_persona: Dict[str, str] = {}
        self.global_persona: int = 1
        self.group_persona: Dict[str, int] = {}
        self.load()

    def load(self):
        if not os.path.exists(self.file_path): self.save(); return
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.user_persona = {str(k): str(v) for k, v in data.get("user_persona", {}).items()}
            self.global_persona = int(data.get("global_persona", 1))
            self.group_persona = {str(k): int(v) for k, v in data.get("group_persona", {}).items() if str(v).isdigit()}
        except Exception as e:
            logger.error(f"加载人设状态失败：{e}")

    def save(self):
        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump({"global_persona": self.global_persona,
                           "user_persona": self.user_persona,
                           "group_persona": self.group_persona},
                          f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存人设状态失败：{e}")

    def _get_persona_item(self, persona_key: str) -> Dict[str, str]:
        if persona_key.isdigit():
            return aichat_config.PERSONA_CATALOG.get(int(persona_key), {})
        return aichat_config.HIDDEN_PERSONA_CATALOG.get(persona_key, {})

    def _valid_persona(self, persona_key: str) -> bool:
        item = self._get_persona_item(persona_key)
        return bool(item) and bool(str(item.get("system_prompt", "")).strip())

    def set_user_persona(self, user_id: str, persona_key: str) -> bool:
        if not self._valid_persona(persona_key): return False
        self.user_persona[str(user_id)] = persona_key; self.save(); return True

    def set_global_persona(self, persona_no: int) -> bool:
        if not self._valid_persona(str(persona_no)): return False
        self.global_persona = persona_no; self.save(); return True

    def get_user_persona(self, user_id: str) -> Optional[str]:
        return self.user_persona.get(str(user_id))

    def set_group_persona(self, group_id: str, persona_no: int) -> bool:
        if persona_no not in aichat_config.PERSONA_CATALOG: return False
        if not self._valid_persona(str(persona_no)): return False
        self.group_persona[str(group_id)] = persona_no; self.save(); return True

    def get_group_persona(self, group_id: str) -> Optional[int]:
        return self.group_persona.get(str(group_id))

    def resolve_persona_key(self, user_id: str, group_id: Optional[str] = None) -> str:
        uc = self.get_user_persona(user_id)
        if uc and self._valid_persona(uc): return uc
        if group_id:
            gc = self.get_group_persona(group_id)
            if gc is not None and gc in aichat_config.PERSONA_CATALOG and self._valid_persona(str(gc)):
                return str(gc)
        if self.global_persona in aichat_config.PERSONA_CATALOG and self._valid_persona(str(self.global_persona)):
            return str(self.global_persona)
        return "1"

    def resolve_system_prompt(self, user_id: str, group_id: Optional[str] = None) -> str:
        pk = self.resolve_persona_key(user_id, group_id)
        sp = str(self._get_persona_item(pk).get("system_prompt", "")).strip()
        return sp or aichat_config.PERSONA_CATALOG.get(1, {}).get("system_prompt", "")

    def get_preview_text(self, user_id: str, extra_desc: str = "",
                         group_id: Optional[str] = None) -> str:
        uc = self.get_user_persona(user_id)
        ak = self.resolve_persona_key(user_id, group_id)
        act = self._get_persona_item(ak)
        gc = self.get_group_persona(group_id) if group_id else None
        lines = [
            f"当前生效人设：#{ak} {act.get('name', '')}",
            f"当前显示名称：{act.get('display_model', '未知')}",
            f"当前说明：{act.get('description', '无')}",
            f"全局人设：#{self.global_persona}",
            f"本群人设：#{gc if gc is not None else '未设置（群聊跟随全局）'}",
            f"你的专属人设：#{uc if uc is not None else '未设置（跟随全局）'}",
            f"API模型：{CONFIG['MODEL_ID']}", "", "可用人设列表："]
        for no in sorted(aichat_config.PERSONA_CATALOG.keys()):
            item = aichat_config.PERSONA_CATALOG[no]
            lines.append(f"#{no} {item.get('name', '')} | 显示={item.get('display_model', '未知')}")
            lines.append(f"说明：{item.get('description', '无')}")
        if extra_desc: lines.extend(["", f"备注：{extra_desc}"])
        return "\n".join(lines)


class QuotaManager:
    def __init__(self, whl_mgr, tdm):
        self.daily_cost = 0.0; self.last_reset_date = date.today()
        self.pending_requests: Dict[str, float] = {}
        self._whitelist = whl_mgr; self._token_daily = tdm

    def reset_daily_quota(self):
        if date.today() != self.last_reset_date:
            self.daily_cost = 0.0; self.last_reset_date = date.today()

    def check_quota_with_reserve(self, request_id: str, amount: float, user_id: str):
        self.reset_daily_quota()
        if self._whitelist.contains(user_id): return True, ""
        if self.daily_cost + amount > CONFIG["DAILY_BUDGET"]:
            return False, f"今日预算不足（已消费{self.daily_cost:.2f}元）"
        return True, ""

    def reserve_quota(self, request_id: str, amount: float, user_id: str):
        if self._whitelist.contains(user_id): return
        self.pending_requests[request_id] = amount

    def update_quota(self, request_id: str, actual_input_tokens: int,
                     actual_output_tokens: int, user_id: str) -> float:
        self.reset_daily_quota()
        if actual_input_tokens > 0 or actual_output_tokens > 0:
            self._token_daily.add(actual_input_tokens, actual_output_tokens)
        if self._whitelist.contains(user_id):
            self.pending_requests.pop(request_id, None); return 0.0
        actual_cost = (actual_input_tokens * CONFIG["INPUT_TOKEN_PRICE"] +
                       actual_output_tokens * CONFIG["OUTPUT_TOKEN_PRICE"])
        self.pending_requests.pop(request_id, 0.0)
        available = CONFIG["DAILY_BUDGET"] - self.daily_cost
        actual_cost = min(actual_cost, available)
        if actual_cost > 0: self.daily_cost += actual_cost
        return actual_cost

    def get_quota_status(self) -> dict:
        self.reset_daily_quota()
        remaining = CONFIG["DAILY_BUDGET"] - self.daily_cost
        pct = (self.daily_cost / CONFIG["DAILY_BUDGET"] * 100) if CONFIG["DAILY_BUDGET"] > 0 else 0
        return {"used": self.daily_cost, "remaining": remaining, "percent": pct, "budget": CONFIG["DAILY_BUDGET"]}

    def cleanup_pending_requests(self):
        now = datetime.now().timestamp()
        for rid in list(self.pending_requests.keys()):
            try:
                if now - float(rid.split("_")[-1]) > 3600:
                    self.pending_requests.pop(rid, None)
            except Exception:
                self.pending_requests.pop(rid, None)


class SessionManager:
    def __init__(self):
        self.sessions: Dict[str, dict] = {}
        self.split_enabled: bool = True  # 全局开关，默认开启
        self.first_chunk: Dict[str, bool] = {}
        self._load_split_state()

    def _load_split_state(self):
        if os.path.exists(SPLIT_STATE_FILE):
            try:
                with open(SPLIT_STATE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # 兼容旧格式（dict）和新格式（bool）
                    if isinstance(data, dict):
                        self.split_enabled = True  # 旧格式迁移：默认开启
                    else:
                        self.split_enabled = bool(data)
            except Exception:
                pass

    def _save_split_state(self):
        try:
            with open(SPLIT_STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(self.split_enabled, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def set_split(self, enabled: bool):
        self.split_enabled = enabled
        self._save_split_state()

    def get_session_key(self, event) -> str:
        if hasattr(event, "group_id") and event.group_id:
            return f"g{event.group_id}u{event.user_id}"
        return f"p{event.user_id}"

    def clear_all_sessions(self):
        self.sessions.clear(); self.first_chunk.clear()


# 全局单例（按依赖顺序初始化）
whitelist_mgr = WhitelistManager(WHITELIST_FILE)
blacklist_mgr = BlacklistManager(BLACKLIST_FILE)
stats_mgr = StatsManager(STATS_FILE)
banwords_mgr = BanwordsManager(BANWORDS_FILE)
persona_mgr = PersonaManager(PERSONA_FILE)
token_daily_mgr = TokenDailyManager(TOKEN_DAILY_FILE)
session_mgr = SessionManager()
quota_mgr = QuotaManager(whitelist_mgr, token_daily_mgr)
stats_counter = stats_mgr
