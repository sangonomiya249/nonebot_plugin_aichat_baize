"""NoneBot2 DeepSeek 对话插件 - 支持 DeepSeek / SiliconFlow API"""
import json
import re
import httpx
import random
from datetime import datetime, date
from typing import Optional

from nonebot import on_message, on_command, logger, get_driver, get_bot
from nonebot.plugin import PluginMetadata
from nonebot.adapters.onebot.v11 import MessageEvent, Message, MessageSegment
from nonebot.rule import to_me
from nonebot.params import CommandArg
from nonebot.matcher import Matcher

from .config import (
    CONFIG, ADMIN_IDS, PERSONA_CATALOG, HIDDEN_PERSONA_CATALOG,
    HIDDEN_PERSONA_WHITELISTS, reload_personas,
)
from .managers import (
    whitelist_mgr, blacklist_mgr, stats_mgr, banwords_mgr,
    persona_mgr, session_mgr, quota_mgr, token_daily_mgr, stats_counter,
    BlacklistManager, WhitelistManager,
)
from .utils import (
    is_command_message, estimate_tokens, split_by_smart, format_reply,
    LOCAL_COMMAND_TRIGGERS, IGNORED_CHAT_PREFIXES, COMMAND_STARTS,
)
from .render import build_persona_preview_image_base64, build_stats_image_base64

__plugin_meta__ = PluginMetadata(
    name="AI对话",
    description="与AI进行智能对话，支持多种管理功能（DeepSeek/SiliconFlow）",
    usage=(
        "- AI对话\n  @机器人 + 消息内容 即可与AI对话\n\n"
        "- 人设管理\n  「/切换人设 + ID」「/人设预览」\n\n"
        "- 管理员指令\n  「/额度」「/重载人设」「/重置额度」\n"
        "  「/清除记忆」「/调用统计」「/切分 (开/关)」"
    ),
    extra={"author": "Baize", "version": "2.0.0"},
)

client = httpx.AsyncClient(
    timeout=httpx.Timeout(connect=15.0, read=CONFIG["REQUEST_TIMEOUT"], write=30.0, pool=15.0),
    transport=httpx.AsyncHTTPTransport(
        retries=CONFIG["MAX_RETRIES"],
        limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
    ),
    default_encoding="utf-8",
)


# ═══════════════════════ Chat 消息处理 ═══════════════════════

ark_chat = on_message(rule=to_me(), priority=98, block=False)


@ark_chat.handle()
async def handle_chat(event: MessageEvent, matcher: Matcher):
    user_id = str(event.user_id)
    group_id = str(event.group_id) if hasattr(event, "group_id") and event.group_id else None
    if blacklist_mgr.is_user_blacklisted(user_id) or (
        group_id and blacklist_mgr.is_group_blacklisted(group_id)
    ):
        return

    request_id = None
    try:
        request_id = f"{user_id}_{datetime.now().timestamp()}"
        user_content = event.get_message().extract_plain_text().strip()
        wake_prefixes = ("钰袖",)
        is_to_me = bool(getattr(event, "to_me", False))
        if (not is_to_me) and (not user_content.startswith(wake_prefixes)):
            return
        for p in wake_prefixes:
            if user_content.startswith(p):
                user_content = user_content[len(p):].lstrip(" ，,：：")
                break
        if not user_content:
            user_content = "在吗"
        elif is_command_message(user_content):
            return

        if banwords_mgr.contains(user_content):
            await matcher.send("我们换一个话题吧"); return

        if not whitelist_mgr.contains(user_id):
            est_input = estimate_tokens(user_content) + 200
            est_output = 800
            est_cost = est_input * CONFIG["INPUT_TOKEN_PRICE"] + est_output * CONFIG["OUTPUT_TOKEN_PRICE"]
            ok, msg = quota_mgr.check_quota_with_reserve(request_id, est_cost, user_id)
            if not ok: await matcher.send(msg); return
            quota_mgr.reserve_quota(request_id, est_cost, user_id)

        stats_counter.update()
        session_key = session_mgr.get_session_key(event)
        now = datetime.now().timestamp()
        session = session_mgr.sessions.get(session_key, {"history": [], "timestamp": now})
        if (now - session["timestamp"]) > CONFIG["SESSION_TIMEOUT"]:
            session["history"] = []
        if isinstance(session["history"], list):
            session["history"].append({"role": "user", "content": user_content})
            session["history"] = session["history"][-CONFIG["MAX_HISTORY"] * 2:]

        buffer = ""
        last_send = datetime.now()
        is_split_mode = session_mgr.split_enabled.get(user_id, True)
        input_tokens = None
        output_tokens = None

        try:
            system_prompt = persona_mgr.resolve_system_prompt(user_id, group_id)
            history_messages = session["history"][-CONFIG["MAX_HISTORY"] * 2:] if session["history"] else []
            messages = [{"role": "system", "content": system_prompt}] + history_messages
            async with client.stream(
                "POST", CONFIG["API_URL"],
                headers={"Authorization": f"Bearer {CONFIG['API_KEY']}",
                         "Content-Type": "application/json"},
                json={"model": CONFIG["MODEL_ID"], "messages": messages,
                      "stream": True, "temperature": 0.7},
            ) as response:
                if response.status_code != 200:
                    logger.error(f"API错误 {response.status_code}")
                    await matcher.send("服务暂时不可用"); return

                async for line in response.aiter_lines():
                    if (datetime.now() - last_send).total_seconds() > CONFIG["REQUEST_TIMEOUT"]:
                        raise httpx.ReadTimeout("响应超时")
                    if line.startswith("data:"):
                        data = line[5:].strip()
                        if data == "[DONE]": break
                        try:
                            chunk = json.loads(data)
                            if "usage" in chunk:
                                input_tokens = chunk["usage"]["prompt_tokens"]
                                output_tokens = chunk["usage"]["completion_tokens"]
                            choices = chunk.get("choices", [{}])
                            if choices and (content := choices[0].get("delta", {}).get("content", "")):
                                buffer += content.replace("�", "").strip()
                                if is_split_mode and buffer:
                                    sentences = split_by_smart(buffer)
                                    if len(sentences) > 1:
                                        need_honor = session_mgr.first_chunk.get(session_key, True)
                                        await matcher.send(format_reply("\n".join(sentences[:-1]), event, need_honor))
                                        session_mgr.first_chunk[session_key] = False
                                        buffer = sentences[-1]
                                        last_send = datetime.now()
                        except json.JSONDecodeError:
                            continue

        except (httpx.ReadTimeout, httpx.ConnectTimeout) as e:
            logger.warning(f"请求超时：{e}")
            await matcher.send("思考需要更多时间呢...")
            try:
                if buffer:
                    await matcher.send(format_reply(buffer, event, not is_split_mode))
                    session["history"].append({"role": "assistant", "content": buffer})
                    if input_tokens is None:
                        input_text = "".join([m["content"] for m in session["history"]])
                        input_tokens = estimate_tokens(input_text)
                        output_tokens = estimate_tokens(buffer)
                    quota_mgr.update_quota(request_id, input_tokens, output_tokens, user_id)
            except Exception:
                pass
            return

        if buffer:
            need_honor = not is_split_mode or session_mgr.first_chunk.get(session_key, True)
            await matcher.send(format_reply(buffer, event, need_honor))
            session["history"].append({"role": "assistant", "content": buffer})
            if input_tokens is None:
                input_text = "".join([m["content"] for m in session["history"]])
                input_tokens = estimate_tokens(input_text)
                output_tokens = estimate_tokens(buffer)
            quota_mgr.update_quota(request_id, input_tokens, output_tokens, user_id)

        session["timestamp"] = now
        session_mgr.sessions[session_key] = session
        session_mgr.first_chunk[session_key] = True

    except Exception as e:
        logger.error(f"处理异常: {repr(e)[:200]}", exc_info=True)
        if request_id: quota_mgr.pending_requests.pop(request_id, None)
        await matcher.send("思考时遇到未知力量阻扰")


# ═══════════════════════ 白名单管理 ═══════════════════════

whitelist_cmd = on_command("白名单", priority=10, block=True)


@whitelist_cmd.handle()
async def handle_whitelist(event: MessageEvent, args: Message = CommandArg()):
    user_id = str(event.user_id)
    if user_id not in ADMIN_IDS:
        await whitelist_cmd.finish("只有管理员才能管理白名单。")
    arg = args.extract_plain_text().strip()
    if not arg:
        lst = whitelist_mgr.list_all()
        await whitelist_cmd.finish(f"当前白名单用户：\n{chr(10).join(lst)}" if lst else "白名单为空。")
    parts = arg.split()
    if len(parts) < 2:
        await whitelist_cmd.finish("用法：白名单 添加/移除 + 用户ID")
    action, target = parts[0], parts[1]
    if action == "添加": whitelist_mgr.add(target); await whitelist_cmd.finish(f"已添加 {target}")
    elif action == "移除": whitelist_mgr.remove(target); await whitelist_cmd.finish(f"已移除 {target}")
    else: await whitelist_cmd.finish("无效操作")


# ═══════════════════════ 黑名单管理 ═══════════════════════

blacklist_cmd = on_command("黑名单", priority=10, block=True)


@blacklist_cmd.handle()
async def handle_blacklist(event: MessageEvent, args: Message = CommandArg()):
    user_id = str(event.user_id)
    if user_id not in ADMIN_IDS:
        await blacklist_cmd.finish("只有管理员才能管理黑名单。")
    arg = args.extract_plain_text().strip()
    if not arg:
        users = "\n".join(blacklist_mgr.list_all_users()) or "无"
        groups = "\n".join(blacklist_mgr.list_all_groups()) or "无"
        await blacklist_cmd.finish(f"黑名单用户：\n{users}\n\n黑名单群聊：\n{groups}")
    parts = arg.split()
    if len(parts) < 3:
        await blacklist_cmd.finish("用法：黑名单 用户/群聊 添加/移除 + ID")
    t, a, v = parts[0], parts[1], parts[2]
    if t == "用户":
        if a == "添加": blacklist_mgr.add_user(v); await blacklist_cmd.finish(f"已添加用户 {v}")
        elif a == "移除": blacklist_mgr.remove_user(v); await blacklist_cmd.finish(f"已移除用户 {v}")
    elif t == "群聊":
        if a == "添加": blacklist_mgr.add_group(v); await blacklist_cmd.finish(f"已添加群聊 {v}")
        elif a == "移除": blacklist_mgr.remove_group(v); await blacklist_cmd.finish(f"已移除群聊 {v}")


# ═══════════════════════ 封禁词管理 ═══════════════════════

banwords_cmd = on_command("封禁词", priority=10, block=True)
add_banword_cmd = on_command("添加封禁词", priority=10, block=True)
remove_banword_cmd = on_command("删除封禁词", priority=10, block=True)


@banwords_cmd.handle()
async def handle_banwords_list(event: MessageEvent):
    if str(event.user_id) not in ADMIN_IDS:
        await banwords_cmd.finish("只有管理员才能查看封禁词。")
    lst = banwords_mgr.list_all()
    await banwords_cmd.finish(f"当前封禁词：\n{chr(10).join(lst)}" if lst else "封禁词为空。")


@add_banword_cmd.handle()
async def handle_add_banword(event: MessageEvent, args: Message = CommandArg()):
    if str(event.user_id) not in ADMIN_IDS:
        await add_banword_cmd.finish("只有管理员才能添加封禁词。")
    w = args.extract_plain_text().strip()
    if not w: await add_banword_cmd.finish("用法：/添加封禁词 xxx")
    banwords_mgr.add(w); await add_banword_cmd.finish(f"已添加封禁词：{w}")


@remove_banword_cmd.handle()
async def handle_remove_banword(event: MessageEvent, args: Message = CommandArg()):
    if str(event.user_id) not in ADMIN_IDS:
        await remove_banword_cmd.finish("只有管理员才能删除封禁词。")
    w = args.extract_plain_text().strip()
    if not w: await remove_banword_cmd.finish("用法：/删除封禁词 xxx")
    if w in banwords_mgr.banwords:
        banwords_mgr.remove(w); await remove_banword_cmd.finish(f"已删除封禁词：{w}")
    else:
        await remove_banword_cmd.finish(f"封禁词中不存在：{w}")


# ═══════════════════════ 人设管理 ═══════════════════════

switch_persona_cmd = on_command("切换人设", priority=10, block=True)
switch_global_persona_cmd = on_command("切换全局人设", priority=10, block=True)
switch_group_persona_cmd = on_command("切换群人设", priority=10, block=True)
persona_preview_cmd = on_command("人设预览", priority=10, block=True)
reload_persona_cmd = on_command("重载人设", priority=10, block=True)


@reload_persona_cmd.handle()
async def handle_reload_persona(event: MessageEvent):
    if str(event.user_id) not in ADMIN_IDS:
        await reload_persona_cmd.finish("只有管理员才能重载人设。")
    try:
        reload_personas()
        await reload_persona_cmd.finish(
            f"人设配置已重新加载！公开{len(PERSONA_CATALOG)}个，隐藏{len(HIDDEN_PERSONA_CATALOG)}个")
    except Exception as e:
        await reload_persona_cmd.finish(f"重载失败：{e}")


@switch_persona_cmd.handle()
async def handle_switch_persona(event: MessageEvent, args: Message = CommandArg()):
    user_id = str(event.user_id)
    arg = args.extract_plain_text().strip()
    if not arg:
        await switch_persona_cmd.finish("用法：/切换人设 + 人设ID")
    pk = arg
    if not pk.isdigit():
        hw = HIDDEN_PERSONA_WHITELISTS.get(pk, set())
        if user_id not in hw:
            await switch_persona_cmd.finish(f"你不在隐藏人设 {pk} 的白名单内。")
    if not persona_mgr.set_user_persona(user_id, pk):
        await switch_persona_cmd.finish(f"切换失败：人设 {pk} 不存在")
    sk = session_mgr.get_session_key(event)
    session_mgr.sessions.pop(sk, None); session_mgr.first_chunk.pop(sk, None)
    p = HIDDEN_PERSONA_CATALOG[pk] if not pk.isdigit() else PERSONA_CATALOG[int(pk)]
    await switch_persona_cmd.finish(
        f"已切换你的人设为 #{pk} {p.get('name','')}（记忆已清除）\n显示：{p.get('display_model','')}")


@switch_global_persona_cmd.handle()
async def handle_switch_global_persona(event: MessageEvent, args: Message = CommandArg()):
    if str(event.user_id) not in ADMIN_IDS:
        await switch_global_persona_cmd.finish("只有管理员才能切换全局人设。")
    arg = args.extract_plain_text().strip()
    if not arg.isdigit():
        await switch_global_persona_cmd.finish("用法：/切换全局人设 + 数字")
    pno = int(arg)
    if not persona_mgr.set_global_persona(pno):
        await switch_global_persona_cmd.finish(f"切换失败：人设 {pno} 不存在")
    p = PERSONA_CATALOG[pno]
    await switch_global_persona_cmd.finish(f"已切换全局人设为 #{pno} {p.get('name','')}")


@switch_group_persona_cmd.handle()
async def handle_switch_group_persona(event: MessageEvent, args: Message = CommandArg()):
    user_id = str(event.user_id)
    if not (hasattr(event, "group_id") and event.group_id):
        await switch_group_persona_cmd.finish("该命令仅可在群聊中使用。")
    sender_role = getattr(getattr(event, "sender", None), "role", "member")
    if sender_role not in ("owner", "admin") and user_id not in ADMIN_IDS:
        await switch_group_persona_cmd.finish("只有群主/群管理员才能切换群人设。")
    arg = args.extract_plain_text().strip()
    if not arg.isdigit():
        await switch_group_persona_cmd.finish("用法：/切换群人设 + 数字")
    pno = int(arg)
    if pno not in PERSONA_CATALOG:
        await switch_group_persona_cmd.finish(f"人设 {pno} 不在目录中")
    if not persona_mgr.set_group_persona(str(event.group_id), pno):
        await switch_group_persona_cmd.finish(f"切换失败")
    p = PERSONA_CATALOG[pno]
    await switch_group_persona_cmd.finish(f"已切换本群人设为 #{pno} {p.get('name','')}")


@persona_preview_cmd.handle()
async def handle_persona_preview(event: MessageEvent, args: Message = CommandArg()):
    user_id = str(event.user_id)
    extra_desc = args.extract_plain_text().strip()
    group_id = str(event.group_id) if hasattr(event, "group_id") and event.group_id else None
    image_b64 = build_persona_preview_image_base64(user_id, extra_desc, group_id)
    if image_b64:
        await persona_preview_cmd.send(Message(MessageSegment.image(f"base64://{image_b64}")))
        return
    await persona_preview_cmd.send(persona_mgr.get_preview_text(user_id, extra_desc, group_id))


# ═══════════════════════ 其他指令 ═══════════════════════

split_control = on_command("切分", priority=10, block=True)


@split_control.handle()
async def handle_split(event: MessageEvent, args: Message = CommandArg()):
    arg = args.extract_plain_text().lower()
    user_id = str(event.user_id)
    reply_map = {("开", "on", "启用"): ("已启用分句模式", True),
                 ("关", "off", "禁用"): ("已禁用分句功能", False)}
    for keywords, (msg, status) in reply_map.items():
        if arg in keywords:
            session_mgr.set_split(user_id, status)
            await split_control.send(f"{msg}（已持久化）"); return
    current = session_mgr.split_enabled.get(user_id, True)
    await split_control.send(f"当前分句状态：{'✅ 启用' if current else '❌ 禁用'}\n使用 /切分 开/关 控制")


clear_memory = on_command("清除记忆", priority=10, block=True)


@clear_memory.handle()
async def handle_clear(event: MessageEvent):
    sk = session_mgr.get_session_key(event)
    if sk in session_mgr.sessions:
        del session_mgr.sessions[sk]; del session_mgr.first_chunk[sk]
        await clear_memory.send("已重置我们的对话")
    else:
        await clear_memory.send("还没有需要清除的记忆哦")


clear_all_memory = on_command("清除所有记忆", aliases={"全局清除记忆"}, priority=10, block=True)


@clear_all_memory.handle()
async def handle_clear_all(event: MessageEvent):
    cnt = len(session_mgr.sessions)
    if cnt == 0: await clear_all_memory.send("当前无会话"); return
    session_mgr.clear_all_sessions()
    await clear_all_memory.send(f"已清除所有会话记忆（共{cnt}个）！")


reset_quota_cmd = on_command("重置额度", aliases={"重置额外"}, priority=10, block=True)


@reset_quota_cmd.handle()
async def handle_reset_quota(event: MessageEvent):
    if str(event.user_id) not in ADMIN_IDS:
        await reset_quota_cmd.finish("只有管理员才能重置额度。")
    quota_mgr.daily_cost = 0.0; quota_mgr.last_reset_date = date.today()
    quota_mgr.pending_requests.clear()
    await reset_quota_cmd.finish("今日额度已手动重置。")


stats_cmd = on_command("调用统计", aliases={"使用统计"}, priority=10, block=True)


@stats_cmd.handle()
async def handle_stats(event: MessageEvent):
    quota_mgr.cleanup_pending_requests()
    stats = stats_counter.get_stats()
    qs = quota_mgr.get_quota_status()
    img = build_stats_image_base64(stats, qs)
    if img:
        await stats_cmd.send(Message(MessageSegment.image(f"base64://{img}")))
    else:
        t = (f"总调用次数：{stats['total_calls']}次\n今日调用：{stats['today_calls']}次\n"
             f"今日费用：{qs['used']:.2f}/{qs['budget']}元\n使用比例：{qs['percent']:.1f}%\n"
             f"活跃会话：{len(session_mgr.sessions)}个")
        await stats_cmd.send(Message(t))


balance_cmd = on_command("额度", aliases={"余额", "查询余额"}, priority=10, block=True)


@balance_cmd.handle()
async def handle_balance(event: MessageEvent):
    user_id = str(event.user_id)
    if user_id not in ADMIN_IDS:
        await balance_cmd.finish("只有管理员才能查询API额度。")
    qs = quota_mgr.get_quota_status()
    api_url = CONFIG["API_URL"]
    is_sf = "siliconflow" in api_url.lower()
    pn = "SiliconFlow" if is_sf else "DeepSeek"

    bt = ""
    try:
        async with httpx.AsyncClient(timeout=15.0) as bc:
            if is_sf:
                base = api_url.rstrip("/").replace("/chat/completions", "").replace("/v1/chat/completions", "")
                resp = await bc.get(f"{base}/user/info",
                                    headers={"Authorization": f"Bearer {CONFIG['API_KEY']}"})
                if resp.status_code == 200:
                    d = resp.json()
                    if isinstance(d, dict):
                        info = d.get("data", {})
                        if isinstance(info, dict):
                            bt = (f"💰 {pn} 账户余额\n可用余额：{info.get('chargeBalance','?')}\n"
                                  f"总余额(含赠送)：{info.get('balance','?')}\n状态：{info.get('status','?')}")
                elif resp.status_code == 401: bt = "❌ API Key 无效"
                else: bt = f"⚠️ 查询失败（HTTP {resp.status_code}）"
            else:
                resp = await bc.get("https://api.deepseek.com/user/balance",
                                    headers={"Authorization": f"Bearer {CONFIG['API_KEY']}"})
                if resp.status_code == 200:
                    d = resp.json()
                    if isinstance(d, dict) and d.get("is_available"):
                        for info in d.get("balance_infos", []):
                            if not isinstance(info, dict): continue
                            bt = (f"💰 {pn} 账户余额（{info.get('currency','CNY')}）\n"
                                  f"总余额：{float(info.get('total_balance',0)):.2f} 元\n"
                                  f"  赠送余额：{float(info.get('granted_balance',0)):.2f} 元\n"
                                  f"  充值余额：{float(info.get('topped_up_balance',0)):.2f} 元")
                    else: bt = f"⚠️ {pn} 账户余额不可用"
                elif resp.status_code == 401: bt = "❌ API Key 无效"
                else: bt = f"⚠️ 查询失败（HTTP {resp.status_code}）"
    except Exception as e:
        logger.warning(f"查询余额失败：{e}")
        bt = f"⚠️ 余额查询失败：{str(e)[:80]}"

    lt = (f"📊 本地预算统计\n今日已消费：{qs['used']:.4f} 元\n今日预算：{qs['budget']:.2f} 元\n"
          f"使用比例：{qs['percent']:.1f}%\n剩余预算：{qs['remaining']:.4f} 元\n活跃会话：{len(session_mgr.sessions)} 个")
    await balance_cmd.finish(f"{bt}\n\n{lt}")


# ═══════════════════════ 启动/关闭 ═══════════════════════

@get_driver().on_startup
async def startup():
    logger.info("DeepSeek AI聊天插件已加载")


@get_driver().on_shutdown
async def shutdown():
    await client.aclose()
    logger.info("DeepSeek AI聊天插件已卸载")
