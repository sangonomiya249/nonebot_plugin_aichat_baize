"""DeepSeek 对话插件 - 工具函数（文本处理、Token估算、命令检测）"""
import re
import os
import random
from typing import List, Set
from nonebot import get_driver

from .config import CONFIG

DRIVER = get_driver()
COMMAND_STARTS = tuple(sorted(
    [s for s in {str(x) for x in getattr(DRIVER.config, "command_start", {"/"})} if s],
    key=len, reverse=True
))
IGNORED_CHAT_PREFIXES = ("#", "/", "／", "end", "yh", "%", "*")


def collect_local_command_triggers() -> Set[str]:
    """扫描当前插件目录中的 on_command 命令词"""
    triggers: Set[str] = set()
    plugin_dir = os.path.dirname(__file__) or "."
    command_re = re.compile(r'on_command\(\s*[rRuUfF]*["\']([^"\']+)["\']')
    aliases_re = re.compile(r"aliases\s*=\s*\{([^}]*)\}", re.S)
    string_re = re.compile(r'[rRuUfF]*["\']([^"\']+)["\']')
    for filename in os.listdir(plugin_dir):
        if not filename.endswith(".py"): continue
        try:
            with open(os.path.join(plugin_dir, filename), "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except Exception: continue
        for m in command_re.finditer(content):
            cmd = m.group(1).strip()
            if cmd: triggers.add(cmd)
        for m in aliases_re.finditer(content):
            for alias in string_re.findall(m.group(1)):
                alias = alias.strip()
                if alias: triggers.add(alias)
    return triggers


LOCAL_COMMAND_TRIGGERS = collect_local_command_triggers()


def is_command_message(text: str) -> bool:
    stripped = text.lstrip()
    if not stripped: return False
    if any(stripped.lower().startswith(p) for p in IGNORED_CHAT_PREFIXES): return True
    first_token = stripped.split(maxsplit=1)[0]
    if first_token in LOCAL_COMMAND_TRIGGERS: return True
    if stripped.startswith(("/", "／")): return True
    if bool(COMMAND_STARTS):
        for p in COMMAND_STARTS:
            if not p: continue
            if stripped.startswith(p):
                remain = stripped[len(p):].lstrip()
                if not remain: return True
                if remain.split(maxsplit=1)[0] in LOCAL_COMMAND_TRIGGERS: return True
                return True
    return False


def estimate_tokens(text: str, is_chinese: bool = True) -> int:
    if not text: return 0
    return len(text) * 2 if is_chinese else int(len(text.split()) * 1.3)


def is_chinese_dominant(text: str, threshold: float = CONFIG["CHINESE_RATIO_THRESHOLD"]) -> bool:
    text_stripped = text.strip()
    if not text_stripped: return False
    chinese_pattern = re.compile(r'[一-鿿]')
    foreign_pattern = re.compile(r'[a-zA-Z぀-ゟ゠-ヿ가-힯Ѐ-ӿ؀-ۿ]')
    chinese_count = len(chinese_pattern.findall(text_stripped))
    foreign_count = len(foreign_pattern.findall(text_stripped))
    total = chinese_count + foreign_count
    if total == 0: return False
    return chinese_count / total >= threshold


def find_insert_position(text: str) -> int:
    if "\n\n" in text: return text.find("\n\n") + 2
    depth, positions = 0, []
    for i, c in enumerate(text):
        if c in "（「【《": depth += 1
        elif c in "）」】》": depth -= 1
        if depth == 0:
            if c in "。！？；～": positions.append(i + 1)
            elif c == "，" and not positions: positions.append(i + 1)
    if positions:
        filtered = [p for p in positions if p > len(text) // 2]
        return random.choice(filtered) if filtered else positions[-1]
    return len(text) // 2 if len(text) > 10 else 0


def format_reply(text: str, event, need_honor: bool) -> str:
    return text


def split_by_smart(text: str) -> List[str]:
    text = re.sub(r"([（「【《])[。！？]", r"\1", text)
    sentences = re.split(r"(?<=[。！？；])", text)
    merged, buf = [], ""
    for s in sentences:
        buf += s
        if len(buf) >= 100: merged.append(buf.strip()); buf = ""
    if buf: merged.append(buf.strip())
    final = []
    for s in merged:
        if not final: final.append(s)
        elif "(" in s and ")" not in s: final[-1] += s
        else: final.append(s)
    return [s for s in final if s]
