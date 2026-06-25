"""DeepSeek 对话插件 - 配置常量（支持 .env 覆盖）"""
import os
import json
import re
from pathlib import Path
from typing import Dict, Set
from nonebot import logger

_ENV_PREFIX = "AICHAT_"

# 手动解析 .env / .env.dev（bot.py 已 os.chdir 到项目根目录）
_env_values: Dict[str, str] = {}
_root = Path.cwd()
for _env_file in [_root / ".env", _root / f".env.{os.environ.get('ENVIRONMENT', '')}"]:
    try:
        if _env_file.exists():
            for _line in _env_file.read_text(encoding="utf-8").splitlines():
                _line = _line.strip()
                if not _line or _line.startswith("#"):
                    continue
                _m = re.match(r'^([A-Z_][A-Z0-9_]*)\s*=\s*(.+)$', _line)
                if _m:
                    _env_values[_m.group(1)] = _m.group(2).strip().strip('"').strip("'")
    except Exception:
        pass

logger.info(f"已从 {_root} 加载环境变量，找到 {len(_env_values)} 个 AICHAT_ 配置项")


def _env(key: str, default):
    """优先读 .env (AICHAT_XXX)，否则用默认值"""
    val = _env_values.get(f"{_ENV_PREFIX}{key}")
    if val is not None and val.strip():
        if isinstance(default, bool):
            return val.lower() in ("true", "1", "yes")
        if isinstance(default, int):
            return int(val)
        if isinstance(default, float):
            return float(val)
        if isinstance(default, set):
            return set(val.replace(" ", "").split(","))
        return val
    return default


# ================= 配置区域 =================
# 所有项都可通过 .env 覆盖，格式: AICHAT_<KEY>=<value>
# 示例: AICHAT_API_KEY=sk-xxx
#       AICHAT_MAX_HISTORY=10
#       AICHAT_ADMIN_IDS=123,456,789
CONFIG = {
    "API_KEY": _env("API_KEY", "sk-your-key-here"),  # API Key（必填，在 .env 中设置 AICHAT_API_KEY=sk-xxx）
    "MODEL_ID": _env("MODEL_ID", "deepseek-chat"),  # 模型名称
    "API_URL": _env("API_URL", "https://api.deepseek.com/chat/completions"),
    "MAX_HISTORY": _env("MAX_HISTORY", 6),  # 保留最近多少轮对话
    "SESSION_TIMEOUT": _env("SESSION_TIMEOUT", 86400),  # 会话超时时间
    "REQUEST_TIMEOUT": _env("REQUEST_TIMEOUT", 140.0),  # 超时时间
    "MAX_RETRIES": _env("MAX_RETRIES", 3),  # 重试次数
    "DAILY_BUDGET": _env("DAILY_BUDGET", 3.0),  # 每日预算（元）
    "INPUT_TOKEN_PRICE": _env("INPUT_TOKEN_PRICE", 1.0 / 1000000),  # 输入Token单价
    "OUTPUT_TOKEN_PRICE": _env("OUTPUT_TOKEN_PRICE", 4.0 / 1000000),  # 输出Token单价
    "CHINESE_RATIO_THRESHOLD": _env("CHINESE_RATIO_THRESHOLD", 0.0),  # 中文占比最低阈值
}

# 管理员列表（.env: AICHAT_ADMIN_IDS=123,456,789）
ADMIN_IDS = _env("ADMIN_IDS", {"12345"})  # type: ignore

# 数据文件路径
WHITELIST_FILE = _env("WHITELIST_FILE", "whitelist.json")  # type: ignore
BLACKLIST_FILE = _env("BLACKLIST_FILE", "blacklist.json")  # type: ignore
STATS_FILE = _env("STATS_FILE", "stats.json")  # type: ignore
BANWORDS_FILE = _env("BANWORDS_FILE", "banwords.json")  # type: ignore
PERSONA_FILE = _env("PERSONA_FILE", "persona_state.json")  # type: ignore
TOKEN_DAILY_FILE = os.path.join(os.path.dirname(__file__) or ".", "token_daily.json")
SPLIT_STATE_FILE = os.path.join(os.path.dirname(__file__) or ".", "split_state.json")
PERSONA_PROMPTS_FILE = os.path.join(os.path.dirname(__file__) or ".", "persona_prompts.json")

# 人设目录（从 JSON 加载）
PERSONA_CATALOG: Dict[int, Dict[str, str]] = {}
HIDDEN_PERSONA_CATALOG: Dict[str, Dict[str, str]] = {}
HIDDEN_PERSONA_WHITELISTS: Dict[str, Set[str]] = {}


def _load_persona_prompts():
    """从 persona_prompts.json 加载所有人设配置"""
    default_public = {
        1: {"name": "默认人设", "system_prompt": "你是一个友好的AI助手，请用中文回复。",
            "display_model": "默认", "description": "默认人设"}
    }
    default_hidden: Dict[str, Dict[str, str]] = {}
    default_whitelists: Dict[str, Set[str]] = {}
    if not os.path.exists(PERSONA_PROMPTS_FILE):
        logger.warning(f"人设配置文件不存在：{PERSONA_PROMPTS_FILE}，使用默认人设")
        return default_public, default_hidden, default_whitelists
    try:
        with open(PERSONA_PROMPTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.error(f"加载人设配置文件失败：{e}")
        return default_public, default_hidden, default_whitelists
    public: Dict[int, Dict[str, str]] = {}
    raw_public = data.get("persona_catalog", {})
    if isinstance(raw_public, dict):
        for k, v in raw_public.items():
            if k.isdigit() and isinstance(v, dict):
                public[int(k)] = {key: str(v.get(key, "")) for key in
                                  ["name", "system_prompt", "display_model", "description"]}
    if not public:
        public = default_public
    hidden: Dict[str, Dict[str, str]] = {}
    raw_hidden = data.get("hidden_persona_catalog", {})
    if isinstance(raw_hidden, dict):
        for k, v in raw_hidden.items():
            if isinstance(v, dict):
                hidden[str(k)] = {key: str(v.get(key, "")) for key in
                                  ["name", "system_prompt", "display_model", "description"]}
    whitelists: Dict[str, Set[str]] = {}
    raw_whitelists = data.get("hidden_persona_whitelists", {})
    if isinstance(raw_whitelists, dict):
        for k, v in raw_whitelists.items():
            if isinstance(v, list):
                whitelists[str(k)] = set(map(str, v))
    logger.info(f"人设配置加载成功：公开{len(public)}个，隐藏{len(hidden)}个")
    return public, hidden, whitelists


def reload_config():
    """重新读取 .env 和 config.py 文件，原地更新 CONFIG"""
    global _env_values
    _env_values.clear()
    # 1) 重读 .env
    for _env_file in [_root / ".env", _root / f".env.{os.environ.get('ENVIRONMENT', '')}"]:
        try:
            if _env_file.exists():
                for _line in _env_file.read_text(encoding="utf-8").splitlines():
                    _line = _line.strip()
                    if not _line or _line.startswith("#"): continue
                    _m = re.match(r'^([A-Z_][A-Z0-9_]*)\s*=\s*(.+)$', _line)
                    if _m:
                        _env_values[_m.group(1)] = _m.group(2).strip().strip('"').strip("'")
        except Exception: pass
    # 2) 从 config.py 文件中提取 _env() 调用的默认值（WebUI 可能改过）
    _file_defaults = {}
    _cfg_path = Path(__file__)
    if _cfg_path.exists():
        try:
            for _line in _cfg_path.read_text(encoding="utf-8").splitlines():
                _m = re.match(r'\s*"(\w+)"\s*:\s*_env\("[^"]*"\s*,\s*"([^"]*)"\)', _line)
                if _m:
                    _file_defaults[_m.group(1)] = _m.group(2)
        except Exception: pass
    CONFIG.update({
        "API_KEY": _env("API_KEY", _file_defaults.get("API_KEY", "sk-your-key-here")),
        "MODEL_ID": _env("MODEL_ID", _file_defaults.get("MODEL_ID", "deepseek-chat")),
        "API_URL": _env("API_URL", _file_defaults.get("API_URL", "https://api.deepseek.com/chat/completions")),
        "MAX_HISTORY": int(_env("MAX_HISTORY", _file_defaults.get("MAX_HISTORY", "6"))),
        "SESSION_TIMEOUT": int(_env("SESSION_TIMEOUT", _file_defaults.get("SESSION_TIMEOUT", "86400"))),
        "REQUEST_TIMEOUT": float(_env("REQUEST_TIMEOUT", _file_defaults.get("REQUEST_TIMEOUT", "140"))),
        "MAX_RETRIES": int(_env("MAX_RETRIES", _file_defaults.get("MAX_RETRIES", "3"))),
        "DAILY_BUDGET": float(_env("DAILY_BUDGET", _file_defaults.get("DAILY_BUDGET", "3"))),
        "INPUT_TOKEN_PRICE": float(_env("INPUT_TOKEN_PRICE", _file_defaults.get("INPUT_TOKEN_PRICE", "1.0"))),
        "OUTPUT_TOKEN_PRICE": float(_env("OUTPUT_TOKEN_PRICE", _file_defaults.get("OUTPUT_TOKEN_PRICE", "4.0"))),
        "CHINESE_RATIO_THRESHOLD": float(_env("CHINESE_RATIO_THRESHOLD", _file_defaults.get("CHINESE_RATIO_THRESHOLD", "0"))),
    })
    logger.info("CONFIG 已从文件刷新，WebUI 修改即时生效")


def reload_personas():
    """运行时重新加载人设配置"""
    global PERSONA_CATALOG, HIDDEN_PERSONA_CATALOG, HIDDEN_PERSONA_WHITELISTS
    PERSONA_CATALOG, HIDDEN_PERSONA_CATALOG, HIDDEN_PERSONA_WHITELISTS = _load_persona_prompts()
    logger.info("人设配置已从文件重新加载")


# 初始加载
reload_personas()

# 启动时打印关键配置（key 脱敏）
_ak = CONFIG.get("API_KEY", "")
_ak_display = _ak[:7] + "***" + _ak[-4:] if len(_ak) > 11 else "***"
logger.info(f"AI 对话插件已加载 | Model={CONFIG.get('MODEL_ID')} | API={CONFIG.get('API_URL')} | Key={_ak_display}")
