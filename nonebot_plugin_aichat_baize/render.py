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

from .config import PERSONA_CATALOG
from .managers import persona_mgr, session_mgr

FONT_PATH_CANDIDATES = [
    os.path.join(os.path.dirname(__file__) or ".", "font.ttf"),
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
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


def _render_persona_preview(user_id: str, extra_desc: str = "",
                             group_id: Optional[str] = None) -> str:
    if not HAS_PIL: return ""
    now = datetime.now()
    akey = persona_mgr.resolve_persona_key(user_id, group_id)
    act = persona_mgr._get_persona_item(akey)
    uch = persona_mgr.get_user_persona(user_id)
    gch = persona_mgr.get_group_persona(group_id) if group_id else None

    bf, mf, xf = _get_font(17), _get_font(14), _get_font(12)
    lgf, ssf = _get_font(24), _get_font(13)
    pub_keys = sorted(PERSONA_CATALOG.keys())
    gap, hh = 14, 80
    row_h = 36
    c1h = 20 + 28 + len(pub_keys) * row_h + 20
    c2h = 20 + 26 + 22 + 16
    c3h = 20 + 28 + 24 + 22 + 20
    th = hh + gap + c1h + gap + c2h + gap + c3h + _P + 24

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

    dr.text((_P, _P + 2), "人设预览", font=lgf, fill=_C["title"])
    dr.text((_P, _P + 34), f"DeepSeek 对话插件  |  {now.strftime('%Y-%m-%d %H:%M')}",
            font=ssf, fill=_C["sub"])
    dr.line([(_P, _P + 58), (_W // 3, _P + 58)], fill=_C["accent_line"], width=3)

    def _card(y, h, label, accent=_C["pink"]):
        dr.rounded_rectangle((_P + 3, y + 3, _W - _P + 3, y + h + 3),
                             radius=16, fill=_C["card_shadow"])
        dr.rounded_rectangle((_P, y, _W - _P, y + h), radius=16, fill=_C["card"])
        dr.text((_P + 20, y + 14), label, font=mf, fill=accent)
        return y + 16 + 28

    cy = hh
    # Card 1: 可切换人设
    c1y = cy; inn = _card(c1y, c1h, "[切换] 可切换人设")
    ry = inn
    clrs = [_C["pink"], _C["violet"], _C["blue"], _C["green"], _C["amber"], _C["rose"]]
    for idx, no in enumerate(pub_keys):
        it = PERSONA_CATALOG[no]
        ds2 = it.get("display_model", ""); dsc2 = it.get("description", "")
        is_act = (str(no) == akey)
        dot_c = _C["green"] if is_act else clrs[idx % len(clrs)]
        dr.ellipse((_P + 22, ry + 6, _P + 32, ry + 16), fill=dot_c)
        rt = f"#{no} {it.get('name', '?')}"
        txt_c = _C["green"] if is_act else _C["text_dark"]
        dr.text((_P + 40, ry + 2), rt, font=bf, fill=txt_c)
        if is_act:
            dw2 = dr.textbbox((0, 0), rt, font=bf)[2]
            dr.text((_P + 40 + dw2 + 8, ry + 3), "<--", font=xf, fill=_C["green"])
        if ds2:
            tx = _P + 40 + 130
            dr.rounded_rectangle((tx, ry + 4, tx + 90, ry + 22), radius=5, fill=_C["tag_bg"])
            dr.text((tx + 6, ry + 5), ds2, font=xf, fill=dot_c)
        if dsc2:
            dr.text((_P + 40, ry + 22), dsc2, font=xf, fill=_C["text_light"])
        ry += row_h
    cy = c1y + c1h + gap

    # Card 2: 人设配置
    c2y = cy; inn = _card(c2y, c2h, "[配置] 人设配置", accent=_C["violet"])
    cx = [_P + 20, _P + 230, _P + 430]
    gi = PERSONA_CATALOG.get(persona_mgr.global_persona, {})
    items = [("全局", f"#{persona_mgr.global_persona} {gi.get('name', '-')}", False)]
    if group_id:
        gd_name = PERSONA_CATALOG.get(gch or 0, {}).get("name", "跟随全局")
        items.append(("本群", f"#{gch} {gd_name}" if gch else "未设置", False))
    else:
        items.append(("本群", "仅私聊", False))
    if uch:
        ui = persona_mgr._get_persona_item(uch)
        items.append(("个人", f"#{uch} {ui.get('name', '-')}", True))
    else:
        items.append(("个人", "跟随全局", False))
    for col_idx, (label, value, highlight) in enumerate(items):
        clr = _C["green"] if highlight else _C["text_dark"]
        dr.text((cx[col_idx], inn), label, font=xf, fill=_C["text_mid"])
        dr.text((cx[col_idx], inn + 18), value, font=mf, fill=clr)
    cy = c2y + c2h + gap

    # Card 3: 当前人设
    c3y = cy; inn = _card(c3y, c3h, "[当前] 当前生效人设", accent=_C["green"])
    nm = act.get("name", "?"); ds = act.get("display_model", "")
    dsc = act.get("description", "")
    nt = f"#{akey} {nm}"
    dw = dr.textbbox((0, 0), nt, font=bf)[2]
    dr.text((_P + 20, inn), nt, font=bf, fill=_C["text_dark"])
    if ds:
        dr.rounded_rectangle((_P + 20 + dw + 12, inn + 3, _P + 20 + dw + 92, inn + 25),
                             radius=6, fill=_C["tag_bg"])
        dr.text((_P + 20 + dw + 18, inn + 4), ds, font=xf, fill=_C["tag_pink"])
    if dsc:
        dr.text((_P + 20, inn + 28), dsc, font=mf, fill=_C["text_mid"])
    dr.text((_P + 20, inn + 50), "使用 /切换人设 <数字> 更换  |  WebUI 管理人设",
            font=xf, fill=_C["text_light"])
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
