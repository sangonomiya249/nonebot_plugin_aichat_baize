"""DeepSeek 对话插件 - PIL 图片渲染（人设预览 + 调用统计）"""
import base64
import io
import os
from datetime import datetime
from typing import Dict, List, Optional

try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

from . import config as aichat_config
from .managers import persona_mgr, session_mgr

FONT_PATH_CANDIDATES = [
    os.path.join(os.path.dirname(__file__) or ".", "font.ttf"),
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
    "/System/Library/Fonts/PingFang.ttc",
]

_font_cache = {}


def _get_font(size: int):
    if size in _font_cache:
        return _font_cache[size]
    for path in FONT_PATH_CANDIDATES:
        try:
            f = ImageFont.truetype(path, size=size)
            _font_cache[size] = f
            return f
        except Exception:
            continue
    f = ImageFont.load_default()
    _font_cache[size] = f
    return f


def _wrap_text(text: str, font, max_w: int, draw) -> List[str]:
    lines = []
    for para in text.split("\n"):
        para = para.strip()
        if not para: lines.append(""); continue
        cur = ""
        for ch in para:
            test = cur + ch
            if draw.textbbox((0, 0), test, font=font)[2] > max_w and cur:
                lines.append(cur); cur = ch
            else: cur = test
        if cur: lines.append(cur)
    return lines


# 调色板
_C = {
    "bg1": (88, 28, 135), "bg2": (59, 30, 120), "bg3": (37, 99, 235),
    "card": (255, 255, 255), "card_shadow": (220, 215, 235),
    "title": (255, 255, 255), "sub": (221, 214, 254),
    "text_dark": (30, 27, 55), "text_mid": (107, 99, 146), "text_light": (130, 120, 165),
    "blue": (59, 130, 246), "pink": (236, 72, 153), "rose": (244, 114, 182),
    "green": (16, 185, 129), "amber": (245, 158, 11), "violet": (139, 92, 246),
    "tag_bg": (252, 231, 243), "tag_pink": (219, 39, 119),
    "accent_line": (236, 72, 153),
}
_W, _P = 720, 28


def _mix(c1, c2, t: float):
    return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))


def _draw_firefly_bg(img, draw, w: int, h: int):
    top = (236, 255, 249)
    mid = (205, 249, 239)
    bottom = (179, 236, 239)
    for y in range(h):
        t = y / max(1, h - 1)
        color = _mix(top, mid, t / 0.58) if t < 0.58 else _mix(mid, bottom, (t - 0.58) / 0.42)
        draw.line([(0, y), (w, y)], fill=color)
    for x in range(-h, w, 58):
        draw.line([(x, 0), (x + h, h)], fill=(158, 224, 215), width=1)
    for x in range(0, w, 96):
        draw.line([(x, 0), (x, h)], fill=(217, 249, 243), width=1)
    for y in range(0, h, 88):
        draw.line([(0, y), (w, y)], fill=(217, 249, 243), width=1)
    for box, fill in (
        ((-150, -110, 310, 270), (178, 255, 225)),
        ((w - 260, -90, w + 130, 260), (143, 230, 206)),
        ((w - 230, h - 300, w + 140, h + 80), (180, 243, 255)),
    ):
        draw.ellipse(box, fill=fill)
    for cx, cy, r in (
        (w - 92, 86, 7), (w - 148, 138, 4), (78, 92, 5),
        (w - 178, h - 108, 5), (132, h - 128, 4),
    ):
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(255, 255, 255))


def _gradient_roundrect(img, box, radius: int, left, right, outline=None, width: int = 1):
    x1, y1, x2, y2 = box
    w, h = x2 - x1, y2 - y1
    patch = Image.new("RGB", (w, h), left)
    pd = ImageDraw.Draw(patch)
    for x in range(w):
        pd.line([(x, 0), (x, h)], fill=_mix(left, right, x / max(1, w - 1)))
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w, h), radius=radius, fill=255)
    img.paste(patch, (x1, y1), mask)
    if outline:
        ImageDraw.Draw(img).rounded_rectangle(box, radius=radius, outline=outline, width=width)


def _text_w(draw, text: str, font) -> int:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0]


def _render_persona_preview(user_id: str, extra_desc: str = "",
                             group_id: Optional[str] = None) -> str:
    if not HAS_PIL: return ""
    now = datetime.now()
    akey = persona_mgr.resolve_persona_key(user_id, group_id)
    act = persona_mgr._get_persona_item(akey)
    uch = persona_mgr.get_user_persona(user_id)
    gch = persona_mgr.get_group_persona(group_id) if group_id else None

    bf, mf, xf = _get_font(22), _get_font(18), _get_font(15)
    lgf, ssf, tinyf = _get_font(38), _get_font(20), _get_font(13)
    persona_catalog = aichat_config.PERSONA_CATALOG
    hidden_persona_catalog = aichat_config.HIDDEN_PERSONA_CATALOG
    pub_keys = sorted(persona_catalog.keys())
    card_w, gap = 408, 18
    cols = 2
    rows = max(1, (len(pub_keys) + cols - 1) // cols)
    row_h = 138
    W = 920
    header_h, status_h, current_h = 170, 128, 150
    list_top = _P + header_h + gap + status_h + gap
    th = list_top + rows * row_h + (rows - 1) * gap + gap + current_h + _P

    img = Image.new("RGB", (W, th), (234, 255, 249)); dr = ImageDraw.Draw(img)
    _draw_firefly_bg(img, dr, W, th)

    _gradient_roundrect(img, (_P, _P, W - _P, _P + header_h), 28,
                        (18, 184, 164), (123, 228, 209),
                        outline=(232, 255, 248), width=3)
    dr.rounded_rectangle((_P + 12, _P + 12, W - _P - 12, _P + header_h - 12),
                         radius=22, outline=(19, 129, 126), width=2)
    dr.text((_P + 30, _P + 28), "FIREFLY PERSONA", font=lgf, fill=(245, 255, 251))
    dr.text((_P + 32, _P + 78), "人设预览 / Persona Catalog", font=ssf, fill=(219, 255, 247))
    dr.text((_P + 32, _P + 112), f"DeepSeek 对话插件  |  {now.strftime('%Y-%m-%d %H:%M')}",
            font=xf, fill=(219, 255, 247))
    dr.line((_P + 32, _P + header_h - 24, W - _P - 190, _P + header_h - 24),
            fill=(9, 120, 118), width=2)
    dr.text((W - _P - 182, _P + 105), "SAM MODE", font=ssf, fill=(231, 255, 249))
    for cx, cy, r in ((W - 110, _P + 54, 8), (W - 154, _P + 88, 5), (W - 78, _P + 116, 4)):
        dr.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(245, 255, 251))

    def chip(x, y, label, value, active=False, wide=250):
        bg = (223, 255, 248) if active else (246, 255, 252)
        bd = (20, 186, 164) if active else (147, 224, 211)
        dr.rounded_rectangle((x, y, x + wide, y + 46), radius=18, fill=bg, outline=bd, width=2)
        dr.text((x + 14, y + 6), label, font=tinyf, fill=(62, 139, 139))
        dr.text((x + 14, y + 22), value, font=xf, fill=(9, 107, 104) if active else (20, 80, 83))

    sy = _P + header_h + gap
    dr.rounded_rectangle((_P, sy, W - _P, sy + status_h), radius=24,
                         fill=(246, 255, 252), outline=(137, 219, 204), width=2)
    gi = persona_catalog.get(persona_mgr.global_persona, {})
    group_text = "仅私聊"
    if group_id:
        gd_name = persona_catalog.get(gch or 0, {}).get("name", "跟随全局")
        group_text = f"#{gch} {gd_name}" if gch else "未设置"
    user_text = "跟随全局"
    if uch:
        ui = persona_mgr._get_persona_item(uch)
        user_text = f"#{uch} {ui.get('name', '-')}"
    chip(_P + 18, sy + 20, "全局人设", f"#{persona_mgr.global_persona} {gi.get('name', '-')}", str(persona_mgr.global_persona) == akey)
    chip(_P + 298, sy + 20, "本群人设", group_text, gch is not None and str(gch) == akey)
    chip(_P + 578, sy + 20, "个人人设", user_text, uch == akey)
    dr.text((_P + 20, sy + 84), f"公开 {len(persona_catalog)} 个  ·  隐藏 {len(hidden_persona_catalog)} 个  ·  当前生效 #{akey}",
            font=xf, fill=(62, 139, 139))

    clrs = [(20, 186, 164), (58, 201, 214), (85, 210, 170), (92, 190, 232), (139, 230, 206), (255, 211, 109)]
    for idx, no in enumerate(pub_keys):
        it = persona_catalog[no]
        col, row = idx % cols, idx // cols
        x = _P + col * (card_w + gap)
        y = list_top + row * (row_h + gap)
        is_act = (str(no) == akey)
        accent = (20, 186, 164) if is_act else clrs[idx % len(clrs)]
        fill = (223, 255, 248) if is_act else (246, 255, 252)
        dr.rounded_rectangle((x, y, x + card_w, y + row_h), radius=22,
                             fill=fill, outline=accent, width=3 if is_act else 2)
        dr.ellipse((x + 18, y + 20, x + 50, y + 52), fill=accent)
        rank = f"#{no}"
        dr.text((x + 60, y + 16), rank, font=mf, fill=(9, 107, 104))
        name = it.get("name", "?")
        dr.text((x + 112, y + 14), name[:12] + ("..." if len(name) > 12 else ""), font=bf, fill=(18, 70, 73))
        ds2 = it.get("display_model", "")
        if ds2:
            pill_w = min(120, max(54, _text_w(dr, ds2, tinyf) + 18))
            dr.rounded_rectangle((x + 60, y + 52, x + 60 + pill_w, y + 78),
                                 radius=10, fill=(205, 255, 244), outline=(137, 219, 204))
            dr.text((x + 69, y + 57), ds2[:9], font=tinyf, fill=(20, 134, 132))
        if is_act:
            dr.rounded_rectangle((x + card_w - 86, y + 18, x + card_w - 20, y + 46),
                                 radius=11, fill=(20, 186, 164))
            dr.text((x + card_w - 72, y + 23), "ACTIVE", font=tinyf, fill=(245, 255, 251))
        dsc2 = it.get("description", "") or "暂无说明"
        desc_lines = _wrap_text(dsc2, xf, card_w - 48, dr)[:2]
        for li, line in enumerate(desc_lines):
            dr.text((x + 24, y + 88 + li * 22), line, font=xf, fill=(62, 139, 139))

    cy = list_top + rows * row_h + (rows - 1) * gap + gap
    dr.rounded_rectangle((_P, cy, W - _P, cy + current_h), radius=26,
                         fill=(225, 255, 248), outline=(20, 186, 164), width=3)
    nm = act.get("name", "?"); ds = act.get("display_model", ""); dsc = act.get("description", "")
    dr.text((_P + 24, cy + 18), f"当前生效人设  #{akey} {nm}", font=bf, fill=(9, 107, 104))
    if ds:
        dw = _text_w(dr, ds, xf) + 22
        dr.rounded_rectangle((_P + 24, cy + 56, _P + 24 + dw, cy + 86), radius=12,
                             fill=(20, 186, 164))
        dr.text((_P + 35, cy + 62), ds, font=xf, fill=(245, 255, 251))
    summary = dsc or "暂无说明"
    if extra_desc:
        summary = f"{summary}  |  {extra_desc}"
    for li, line in enumerate(_wrap_text(summary, mf, W - _P * 2 - 48, dr)[:2]):
        dr.text((_P + 24, cy + 96 + li * 25), line, font=mf, fill=(20, 80, 83))
    dr.text((W - _P - 280, cy + current_h - 34), "/切换人设 <ID>  |  WebUI 管理人设",
            font=xf, fill=(62, 139, 139))
    buf = io.BytesIO(); img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def _render_stats_image(stats: Dict, quota_status: Dict) -> str:
    if not HAS_PIL: return ""
    now = datetime.now(); th = 400
    img = Image.new("RGB", (_W, th), _C["bg1"]); dr = ImageDraw.Draw(img)
    for i in range(th):
        q = i / th
        if q < 0.5:
            q2 = q * 2
            r = int(88 + (59 - 88) * q2); g = int(28 + (30 - 28) * q2); b = int(135 + (120 - 135) * q2)
        else:
            q2 = (q - 0.5) * 2
            r = int(59 + (37 - 59) * q2); g = int(30 + (99 - 30) * q2); b = int(120 + (235 - 120) * q2)
        dr.line([(0, i), (_W, i)], fill=(r, g, b))
    lgf, ssf, bf = _get_font(24), _get_font(13), _get_font(38)
    dr.text((_P, _P), "调用统计", font=lgf, fill=_C["title"])
    dr.text((_P, _P + 32), f"DeepSeek 对话插件  |  {now.strftime('%Y-%m-%d %H:%M')}",
            font=ssf, fill=_C["sub"])
    dr.line([(_P, _P + 54), (_W // 3, _P + 54)], fill=_C["accent_line"], width=3)
    clrs = [_C["pink"], _C["green"], _C["amber"], _C["violet"]]
    mt = [("总调用次数", f"{stats['total_calls']}", "次"),
          ("今日调用", f"{stats['today_calls']}", "次"),
          ("今日费用", f"{quota_status['used']:.4f}", f"/ {quota_status['budget']} 元"),
          ("活跃会话", f"{len(session_mgr.sessions)}", "个")]
    y = 100
    for idx, (lb, vl, unit) in enumerate(mt):
        cl = clrs[idx]
        dr.rounded_rectangle((_P, y, _P + 6, y + 50), radius=3, fill=cl)
        dr.text((_P + 16, y), lb, font=ssf, fill=_C["text_light"])
        dr.text((_P + 16, y + 18), vl, font=bf, fill=cl)
        uw = dr.textbbox((0, 0), vl, font=bf)[2]
        dr.text((_P + 16 + uw + 6, y + 35), unit, font=ssf, fill=_C["text_mid"])
        y += 66
    buf = io.BytesIO(); img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def build_persona_preview_image_base64(user_id: str, extra_desc: str = "",
                                       group_id: Optional[str] = None) -> str:
    return _render_persona_preview(user_id, extra_desc, group_id)


def build_stats_image_base64(stats: Dict, quota_status: Dict) -> str:
    return _render_stats_image(stats, quota_status)
