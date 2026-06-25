"""DeepSeek 对话插件 - 配置常量（支持 .env 覆盖）"""
import os
import json
from typing import Dict, Set
from nonebot import logger, get_driver

_driver = get_driver()
_ENV_PREFIX = "AICHAT_"


def _env(key: str, default):
    """优先读 .env (AICHAT_XXX=value)，否则用默认值"""
    val = getattr(_driver.config, f"{_ENV_PREFIX}{key}", None)
    if val is not None:
        if isinstance(default, bool):
            return str(val).lower() in ("true", "1", "yes")
        if isinstance(default, int):
            return int(val)
        if isinstance(default, float):
            return float(val)
        if isinstance(default, set):
            return set(str(val).replace(" ", "").split(","))
        return str(val)
    return default


# ================= 配置区域 =================
# 所有项都可通过 .env 覆盖，格式: AICHAT_<KEY>=<value>
# 示例: AICHAT_API_KEY=sk-xxx
#       AICHAT_MAX_HISTORY=10
#       AICHAT_ADMIN_IDS=123,456,789
CONFIG = {
    "API_KEY": _env("API_KEY", "sk-你的密钥"),  # API Key
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
ADMIN_IDS = _env("ADMIN_IDS", {"2491434931", "1435219086", "3469915084"})  # type: ignore

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


def reload_personas():
    """运行时重新加载人设配置"""
    global PERSONA_CATALOG, HIDDEN_PERSONA_CATALOG, HIDDEN_PERSONA_WHITELISTS
    PERSONA_CATALOG, HIDDEN_PERSONA_CATALOG, HIDDEN_PERSONA_WHITELISTS = _load_persona_prompts()
    logger.info("人设配置已从文件重新加载")


# 初始加载
reload_personas()
