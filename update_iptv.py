#!/usr/bin/env python3
"""
IPTV Auto-updater
- Nguồn: Danh sách M3U tổng hợp / sưu tập
- Kênh TV: VTV, ANQP, HTV, VTVcab, SCTV, địa phương
- EPG: Tự động tải, sửa múi giờ Việt Nam (+0700) và xuất file iptv.epg.xml
- Sắp xếp địa phương: Tên tỉnh thành A-Z (63 tỉnh thành)
- tvg-id chuẩn hóa theo vnepg (viết liền, không dấu gạch ngang)
- Output: http-iptv.m3u, my_list.m3u & iptv.epg.xml
"""

import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Final, Optional

import requests

# ──────────────────────────────────────────────────────────────────────
# CẤU HÌNH
# ──────────────────────────────────────────────────────────────────────
SOURCES: Final[list[str]] = [
    #___Để chọn nhiều nguồn khác nhau chỉ cần xoá bỏ # ở trước links nguồn _______
    
    "https://dl.dropboxusercontent.com/s/o5vygit34v9ryly71gam4/coban66.m3u?rlkey=auyoon54hfubajt16nc7u7dbn&st=70gyvtcu&dl=0",
    # "https://raw.githubusercontent.com/quanlehong539/TVPub/patch-3/TVPub%20IPTV",
    "https://1.org.vn/vmttv",
    # "https://vmttv.duckdns.org/",
    # "https://raw.githubusercontent.com/iptv-org/iptv/refs/heads/master/streams/vn.m3u",
]

RAW_EPG_SOURCE: Final[str] = "https://epg.io.vn/epgu.xml"
EPG_OUTPUT_FILE: Final[str] = "iptv.epg.xml"
MY_EPG_URL: Final[str] = f"https://raw.githubusercontent.com/MFT-T/diwi-iptv/main/{EPG_OUTPUT_FILE}"
OUTPUT_FILE: Final[str] = "http-iptv.m3u"
GLOBAL_TIMEOUT: Final[int] = 20
HTTP_HEADERS: Final[dict[str, str]] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

# ──────────────────────────────────────────────────────────────────────
# REGEX PRE-COMPILED
# ──────────────────────────────────────────────────────────────────────
_NORM_RE = re.compile(r"\s+")
_DEDUP_RE = re.compile(r"[\s\-._]+")
_BITRATE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*mb(?:ps)?", re.I)
_NOISE_RE = re.compile(
    r"[\s\-–|]*\b(?:fhd|full\s*hd|hd|sd|4k|8k|uhd|h\.?264|h\.?265|hevc|avc"
    r"|\d+(?:\.\d+)?\s*mbps|\d+\s*kbps)\b.*$",
    re.IGNORECASE,
)
_PIPE_RE = re.compile(r"\s*\|.*$")
_MULTI_SPACE_RE = re.compile(r"\s{2,}")
_TVG_ID_RE = re.compile(r'tvg-id="([^"]*)"')
_TVG_LOGO_RE = re.compile(r'tvg-logo="([^"]*)"')
_GROUP_TITLE_RE = re.compile(r'group-title="([^"]*)"')

_QUALITY_TIERS: Final[list[tuple[re.Pattern, int]]] = [
    (re.compile(r"\b8k\b", re.I), 80),
    (re.compile(r"\b4k\b|\buhd\b", re.I), 70),
    (re.compile(r"\bfhd\b|\bfull\s*hd\b", re.I), 60),
    (re.compile(r"\bhd\b", re.I), 50),
    (re.compile(r"\bsd\b", re.I), 20),
]


def _norm_key(s: str) -> str:
    return _NORM_RE.sub("", s).upper()


def _dedup_key(name: str) -> str:
    return _DEDUP_RE.sub("", name.lower())


# ──────────────────────────────────────────────────────────────────────
# CHUẨN HÓA TVG-ID THEO VNEPG
# ──────────────────────────────────────────────────────────────────────
TVG_ID_MAP: Final[dict[str, str]] = {
    "vtv6": "vtv6hd",
    "vtv10": "vtv10hd",
    "htv1": "htv1hd",
    "htv3": "htv3hd",
    "htv4": "htv4hd",
    "htvccanhachd": "htvccanachd",
    "htvcthuanviet": "htvcthuanviethd",
    "antv-hd": "antv",
    "qpvn-hd": "qpvn",
    "tayninhtv": "tayninh1",
    "dongthap": "dongthap1",
    "cantho": "cantho1",
    "lamdong": "lamdong1",
    "ltv": "laichau",
    "thvl1hd": "vinhlong1hd",
    "thvl1": "vinhlong1hd",
    "thvl2hd": "vinhlong2hd",
    "thvl2": "vinhlong2hd",
    "thvl3hd": "vinhlong3hd",
    "thvl3": "vinhlong3hd",
    "thvl4hd": "vinhlong4hd",
    "thvl4": "vinhlong4hd",
    "thvl5hd": "vinhlong5hd",
    "thvl5": "vinhlong5hd",
}


def normalize_tvg_id(raw_id: str) -> str:
    clean = raw_id.strip().lower()
    return TVG_ID_MAP.get(clean, clean.replace("-", ""))


# ──────────────────────────────────────────────────────────────────────
# DỮ LIỆU KÊNH
# ──────────────────────────────────────────────────────────────────────
_CHANNEL_DATA: Final[dict[str, tuple[str, str]]] = {
    # ── VTV ──────────────────────────────────────────────────────────
    "vtv1hd": ("VTV1", "VTV"),
    "vtv2hd": ("VTV2", "VTV"),
    "vtv3hd": ("VTV3", "VTV"),
    "vtv4hd": ("VTV4", "VTV"),
    "vtv5hd": ("VTV5", "VTV"),
    "vtv5hdtnb": ("VTV5 Tây Nam Bộ", "VTV"),
    "vtv5hdtn": ("VTV5 Tây Nguyên", "VTV"),
    "vtv6hd": ("VTV6", "VTV"),
    "vtv7hd": ("VTV7", "VTV"),
    "vtv8hd": ("VTV8", "VTV"),
    "vtv9hd": ("VTV9", "VTV"),
    "vtv10hd": ("VTV10", "VTV"),
    "vietnamtoday": ("Vietnam Today", "VTV"),
    
    #_________ANQP_________
    
    "antvhd": ("ANTV", "ANQP"),
    "qpvnhd": ("QPVN", "ANQP"),
    # ── HTV / HTVC ───────────────────────────────────────────────────
    "htv1hd": ("HTV1", "HTV"),
    "htv2hd": ("HTV2", "HTV"),
    "htv3hd": ("HTV3", "HTV"),
    "htv4hd": ("HTV4", "HTV"),
    "htv5": ("HTV5", "HTV"),
    "htv7hd": ("HTV7", "HTV"),
    "htv9hd": ("HTV9", "HTV"),
    "htvthethaohd": ("HTVC Thể Thao", "HTV"),
    "htvccanachd": ("HTVC Ca Nhạc", "HTV"),
    "htvcdulichhd": ("HTVC Du Lịch", "HTV"),
    "htvcgiadinhhd": ("HTVC Gia Đình", "HTV"),
    "htvcphimhd": ("HTVC Phim", "HTV"),
    "htvcphunuhd": ("HTVC Phụ Nữ", "HTV"),
    "htvcthuanviethd": ("HTVC Thuần Việt", "HTV"),
    "htvcplushd": ("HTVC+", "HTV"),
    # ── VTVcab ───────────────────────────────────────────────────────
    "onphimviet": ("ON Phim Việt", "VTVcab"),
    "ongolf": ("ON Golf", "VTVcab"),
    "OnHomeShopping": ("ON HomeShopping", "VTVcab"),
    "onkids": ("ON Kids", "VTVcab"),
    "onlife": ("ON Life", "VTVcab"),
    "onmovies": ("ON Movies", "VTVcab"),
    "onviedramas": ("ON Vie DRAMAS", "VTVcab"),
    "TVBVietnam.vn@SD": ("TVB ViệtNam", "VTVcab"),
    # ── SCTV ─────────────────────────────────────────────────────────
    "sctv2hd": ("SCTV2", "SCTV"),
    "sctv3hd": ("SCTV3", "SCTV"),
    "sctv4hd": ("SCTV4", "SCTV"),
    "sctv6hd": ("SCTV6", "SCTV"),
    "sctv7hd": ("SCTV7", "SCTV"),
    "sctv9hd": ("SCTV9", "SCTV"),
    "sctv11hd": ("SCTV11", "SCTV"),
    "sctv12hd": ("SCTV12", "SCTV"),
    "sctv13hd": ("SCTV13", "SCTV"),
    "sctv14hd": ("SCTV14", "SCTV"),
    "sctv16hd": ("SCTV16", "SCTV"),
    "sctv18hd": ("SCTV18", "SCTV"),
    "sctv19hd": ("SCTV19", "SCTV"),
    "sctv20hd": ("SCTV20", "SCTV"),
    # ── ĐỊA PHƯƠNG — Miền Bắc ────────────────────────────────────────
    "hagiang": ("Hà Giang", "Hà Giang"),
    "tuyenquang": ("Tuyên Quang", "Tuyên Quang"),
    "caobang": ("Cao Bằng", "Cao Bằng"),
    "langson": ("Lạng Sơn", "Lạng Sơn"),
    "backan": ("Bắc Kạn", "Bắc Kạn"),
    "thainguyen": ("Thái Nguyên", "Thái Nguyên"),
    "quangninh1": ("Quảng Ninh 1", "Quảng Ninh"),
    "quangninh3": ("Quảng Ninh 3", "Quảng Ninh"),
    "bacgiang": ("Bắc Giang", "Bắc Giang"),
    "bacninh": ("Bắc Ninh", "Bắc Ninh"),
    "laocai": ("Lào Cai", "Lào Cai"),
    "yenbai": ("Yên Bái", "Yên Bái"),
    "phutho": ("Phú Thọ", "Phú Thọ"),
    "vinhphuc": ("Vĩnh Phúc", "Vĩnh Phúc"),
    "hanoi1": ("Hà Nội 1", "Hà Nội"),
    "hanoi2": ("Hà Nội 2", "Hà Nội"),
    "hoabinh": ("Hòa Bình", "Hòa Bình"),
    "sonla": ("Sơn La", "Sơn La"),
    "dienbien": ("Điện Biên", "Điện Biên"),
    "laichau": ("Lai Châu", "Lai Châu"),
    "haiphong": ("Hải Phòng", "Hải Phòng"),
    "haiphong3": ("Hải Phòng 3", "Hải Phòng"),
    "haiphongplus": ("Hải Phòng +", "Hải Phòng"),
    "haiduong": ("Hải Dương", "Hải Dương"),
    "hungyen": ("Hưng Yên", "Hưng Yên"),
    "thaibinh": ("Thái Bình", "Thái Bình"),
    "namdinh": ("Nam Định", "Nam Định"),
    "hanam": ("Hà Nam", "Hà Nam"),
    "ninhbinh": ("Ninh Bình", "Ninh Bình"),
    # ── ĐỊA PHƯƠNG — Miền Trung ──────────────────────────────────────
    "thanhhoa": ("Thanh Hóa", "Thanh Hóa"),
    "nghean": ("Nghệ An", "Nghệ An"),
    "hatinh": ("Hà Tĩnh", "Hà Tĩnh"),
    "quangbinh": ("Quảng Bình", "Quảng Bình"),
    "quangtri": ("Quảng Trị", "Quảng Trị"),
    "hue": ("Huế", "Thừa Thiên Huế"),
    "danang1": ("Đà Nẵng 1", "Đà Nẵng"),
    "danang2": ("Đà Nẵng 2", "Đà Nẵng"),
    "quangnam": ("Quảng Nam", "Quảng Nam"),
    "quangngai": ("Quảng Ngãi 1", "Quảng Ngãi"),
    "quangngai2": ("Quảng Ngãi 2", "Quảng Ngãi"),
    "binhdinh": ("Bình Định", "Bình Định"),
    "phuyen": ("Phú Yên", "Phú Yên"),
    "khanhhoa": ("Khánh Hòa", "Khánh Hòa"),
    "khanhhoa1": ("Khánh Hòa 1", "Khánh Hòa"),
    "khanhhoa2": ("Khánh Hòa 2", "Khánh Hòa"),
    "ninhthuan": ("Ninh Thuận", "Ninh Thuận"),
    "binhthuan": ("Bình Thuận", "Bình Thuận"),
    # ── ĐỊA PHƯƠNG — Tây Nguyên ──────────────────────────────────────
    "kontum": ("Kon Tum", "Kon Tum"),
    "gialai": ("Gia Lai", "Gia Lai"),
    "daklak": ("Đắk Lắk", "Đắk Lắk"),
    "daknong": ("Đắk Nông", "Đắk Nông"),
    "lamdong1": ("Lâm Đồng 1", "Lâm Đồng"),
    "lamdong2": ("Lâm Đồng 2", "Lâm Đồng"),
    # ── ĐỊA PHƯƠNG — Miền Nam ────────────────────────────────────────
    "binhphuoc": ("Bình Phước", "Bình Phước"),
    "tayninh1": ("Tây Ninh", "Tây Ninh"),
    "binhduong": ("Bình Dương", "Bình Dương"),
    "dongnai1": ("Đồng Nai 1", "Đồng Nai"),
    "dongnai2": ("Đồng Nai 2", "Đồng Nai"),
    "DongNaiTV3.vn@SD": ("Đồng Nai 3", "Đồng Nai"),
    "baria": ("Bà Rịa - Vũng Tàu", "Bà Rịa - Vũng Tàu"),
    "longan": ("Long An", "Long An"),
    "tiengiang": ("Tiền Giang", "Tiền Giang"),
    "bentre": ("Bến Tre", "Bến Tre"),
    "dongthap1": ("Đồng Tháp 1", "Đồng Tháp"),
    "dongthap2": ("Đồng Tháp 2", "Đồng Tháp"),
    "vinhlong1hd": ("Vĩnh Long 1", "Vĩnh Long"),
    "vinhlong2hd": ("Vĩnh Long 2", "Vĩnh Long"),
    "vinhlong3hd": ("Vĩnh Long 3", "Vĩnh Long"),
    "vinhlong4hd": ("Vĩnh Long 4", "Vĩnh Long"),
    "vinhlong5hd": ("Vĩnh Long 5", "Vĩnh Long"),
    "travinh": ("Trà Vinh", "Trà Vinh"),
    "angiang1": ("An Giang 1", "An Giang"),
    "angiang2": ("An Giang 2", "An Giang"),
    "angiang3": ("An Giang 3", "An Giang"),
    "kiengiang": ("Kiên Giang", "Kiên Giang"),
    "cantho1": ("Cần Thơ 1", "Cần Thơ"),
    "cantho2": ("Cần Thơ 2", "Cần Thơ"),
    "cantho3": ("Cần Thơ 3", "Cần Thơ"),
    "haugiang": ("Hậu Giang", "Hậu Giang"),
    "soctrang": ("Sóc Trăng", "Sóc Trăng"),
    "baclieu": ("Bạc Liêu", "Bạc Liêu"),
    "camau": ("Cà Mau", "Cà Mau"),
}

_KNOWN_IDS: Final[frozenset[str]] = frozenset(_CHANNEL_DATA)

# ──────────────────────────────────────────────────────────────────────
# THỨ TỰ HIỂN THỊ & INDEX SORT
# ──────────────────────────────────────────────────────────────────────
_VTV_ORDER: Final[list[str]] = [
    "VTV1", "VTV2", "VTV3", "VTV4", "VTV5", "VTV5 Tây Nam Bộ",
    "VTV5 Tây Nguyên", "VTV6", "VTV7", "VTV8", "VTV9", "VTV10", "VietNamToDay"
]
_ANQP_ORDER: Final[list[str]] = [
    "ANTV", "QPVN"
]
_HTV_ORDER: Final[list[str]] = [
    "HTV1", "HTV2", "HTV3", "HTV4", "HTV5", "HTV7", "HTV9", "HTVC+",
    "HTVC Ca Nhạc", "HTVC Du Lịch", "HTVC Gia Đình", "HTVC Phim",
    "HTVC Phụ Nữ", "HTVC Thể Thao", "HTVC Thuần Việt"
]
_VTVcab_ORDER: Final[list[str]] = [
    "ON Golf", "ON HomeShopping", "ON Kids", "ON Life", "ON Movies", "ON Phim Việt", "ON Vie DRAMAS", "TVB ViệtNam"
]
_SCTV_ORDER: Final[list[str]] = [
    "SCTV2", "SCTV3", "SCTV4", "SCTV6", "SCTV7", "SCTV9", "SCTV11", "SCTV12", "SCTV13", "SCTV14", "SCTV16", "SCTV18", "SCTV19", "SCTV20"
]
_PROVINCE_ORDER: Final[list[str]] = [
    "An Giang", "Bà Rịa - Vũng Tàu", "Bạc Liêu", "Bắc Giang", "Bắc Kạn", "Bắc Ninh",
    "Bến Tre", "Bình Định", "Bình Dương", "Bình Phước", "Bình Thuận", "Cà Mau",
    "Cao Bằng", "Cần Thơ", "Đà Nẵng", "Đắk Lắk", "Đắk Nông", "Điện Biên",
    "Đồng Nai", "Đồng Tháp", "Gia Lai", "Hà Giang", "Hà Nam", "Hà Nội",
    "Hà Tĩnh", "Hải Dương", "Hải Phòng", "Hậu Giang", "Hòa Bình", "Thừa Thiên Huế", "Hưng Yên", 
    "Khánh Hòa", "Kiên Giang", "Kon Tum", "Lai Châu", "Lạng Sơn", "Lào Cai",
    "Lâm Đồng", "Long An", "Nam Định", "Nghệ An", "Ninh Bình", "Ninh Thuận",
    "Phú Thọ", "Phú Yên", "Quảng Bình", "Quảng Nam", "Quảng Ngãi", "Quảng Ninh",
    "Quảng Trị", "Sóc Trăng", "Sơn La", "Tây Ninh", "Thái Bình", "Thái Nguyên",
    "Thanh Hóa", "Tiền Giang", "Trà Vinh", "Tuyên Quang", "Vĩnh Long",
    "Vĩnh Phúc", "Yên Bái"
]

_GROUP_ORDER: Final[dict[str, int]] = {"VTV": 0, "ANQP": 1, "HTV": 2, "VTVcab": 3, "SCTV": 4, "LOCAL": 5}
_VTV_IDX: Final[dict[str, int]] = {_norm_key(n): i for i, n in enumerate(_VTV_ORDER)}
_HTV_IDX: Final[dict[str, int]] = {_norm_key(n): i for i, n in enumerate(_HTV_ORDER)}
_VTVcab_IDX: Final[dict[str, int]] = {_norm_key(n): i for i, n in enumerate(_VTVcab_ORDER)}
_SCTV_IDX: Final[dict[str, int]] = {_norm_key(n): i for i, n in enumerate(_SCTV_ORDER)}
_ANQP_IDX: Final[dict[str, int]] = {_norm_key(n): i for i, n in enumerate(_ANQP_ORDER)}
_PROVINCE_IDX: Final[dict[str, int]] = {p: i for i, p in enumerate(_PROVINCE_ORDER)}

_LABEL: Final[dict[str, str]] = {
    "VTV": "VTV",
    "ANQP": "ANQP",
    "HTV": "HTV",
    "VTVcab": "VTVcab",
    "SCTV": "SCTV",
    "LOCAL": "Địa phương"
}

_LOCAL_KEYWORDS: Final[frozenset[str]] = frozenset(
    ["địa phương", "dia phuong", "tỉnh", "tinh"]
)

_NOISE_NAMES: Final[frozenset[str]] = frozenset(
    ["SỰ KIỆN", "VTVPRIME", "FPT", "VOV", "O2"]
)

# ──────────────────────────────────────────────────────────────────────
# DATA MODEL & HELPER
# ──────────────────────────────────────────────────────────────────────
@dataclass(slots=True)
class Channel:
    name: str
    url: str
    group_key: str
    province: str
    province_idx: int
    quality: tuple[int, float]
    tvg_id: str = ""
    tvg_logo: str = ""

    @property
    def group_label(self) -> str:
        return _LABEL[self.group_key]


def quality_score(raw: str) -> tuple[int, float]:
    tier = 40
    for pat, score in _QUALITY_TIERS:
        if pat.search(raw):
            tier = score
            break
    m = _BITRATE_RE.search(raw)
    return tier, float(m.group(1)) if m else 0.0


def fetch(url: str) -> Optional[str]:
    try:
        r = requests.get(url, timeout=GLOBAL_TIMEOUT, headers=HTTP_HEADERS)
        r.raise_for_status()
        return r.text
    except Exception as e:
        print(f"  ⚠  {url}: {e}", file=sys.stderr)
        return None


def resolve_display_name(raw: str, tvg_id: str) -> str:
    if tvg_id:
        entry = _CHANNEL_DATA.get(tvg_id)
        if entry:
            return entry[0]
    s = _NOISE_RE.sub("", raw).strip()
    s = _PIPE_RE.sub("", s).strip()
    return _MULTI_SPACE_RE.sub(" ", s) or raw.strip()


def _classify(tvg_id: str, src_grp: str) -> Optional[str]:
    grp = src_grp.lower()
    if "vtv" in grp:
        return "VTV"
    if "htv" in grp:
        return "HTV"
    if "vtvcab" in grp:
        return "VTVcab"
    if "sctv" in grp:
        return "SCTV"
    if "anqp" in grp:
        return "ANQP"
    if any(kw in grp for kw in _LOCAL_KEYWORDS):
        return "LOCAL"
    if "quốc phòng" in grp or "quoc phong" in grp:
        return "ANQP"

    if tvg_id in _KNOWN_IDS:
        tag = _CHANNEL_DATA[tvg_id][1]
        return tag if tag in ("VTV", "HTV", "VTVcab", "SCTV", "ANQP") else "LOCAL"
    if tvg_id.startswith("vtv"):
        return "VTV"
    if tvg_id.startswith("htv"):
        return "HTV"
    if tvg_id.startswith("vtvcab"):
        return "VTVcab"
    if tvg_id.startswith("sctv"):
        return "SCTV"
    if tvg_id.startswith("anqp"):
        return "ANQP"
    return None


def _is_noise(tvg_id: str, upper_name: str) -> bool:
    return any(kw in upper_name for kw in _NOISE_NAMES)

# ──────────────────────────────────────────────────────────────────────
# PARSER, MERGE, SORT & WRITE
# ──────────────────────────────────────────────────────────────────────
def parse_m3u(text: str) -> list[Channel]:
    channels: list[Channel] = []
    current_extinf: Optional[str] = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#EXTINF"):
            current_extinf = line
            continue
        if line.startswith("#") or not current_extinf:
            continue

        extinf_line, current_extinf = current_extinf, None
        url = line

        m_id = _TVG_ID_RE.search(extinf_line)
        m_logo = _TVG_LOGO_RE.search(extinf_line)
        m_grp = _GROUP_TITLE_RE.search(extinf_line)

        tvg_id = normalize_tvg_id(m_id.group(1)) if m_id else ""
        tvg_logo = m_logo.group(1).strip() if m_logo else ""
        src_grp = m_grp.group(1).strip() if m_grp else ""
        raw_name = extinf_line.split(",", 1)[-1].strip() if "," in extinf_line else ""

        if not raw_name or _is_noise(tvg_id, raw_name.upper()):
            continue

        group_key = _classify(tvg_id, src_grp)
        if group_key is None:
            continue

        province = ""
        province_idx = 999
        if group_key == "LOCAL":
            entry = _CHANNEL_DATA.get(tvg_id)
            if not entry:
                continue
            province = entry[1]
            province_idx = _PROVINCE_IDX.get(province, 999)

        channels.append(
            Channel(
                name=resolve_display_name(raw_name, tvg_id),
                url=url,
                group_key=group_key,
                province=province,
                province_idx=province_idx,
                quality=quality_score(raw_name),
                tvg_id=tvg_id,
                tvg_logo=tvg_logo,
            )
        )

    return channels


def merge_sources(lists: list[list[Channel]]) -> list[Channel]:
    best: dict[str, Channel] = {}
    seen_urls: set[str] = set()

    for ch in (ch for lst in lists for ch in lst):
        url = ch.url.strip()
        if url in seen_urls:
            continue
        key = _dedup_key(ch.name)
        existing = best.get(key)
        if existing is None or ch.quality > existing.quality:
            if existing is not None:
                seen_urls.discard(existing.url.strip())
            best[key] = ch
            seen_urls.add(url)

    return list(best.values())


def sort_channels(channels: list[Channel]) -> list[Channel]:
    def key(ch: Channel) -> tuple:
        g = _GROUP_ORDER[ch.group_key]
        norm_n = _norm_key(ch.name)
        if ch.group_key == "VTV":
            return (g, _VTV_IDX.get(norm_n, 999), ch.name)
        if ch.group_key == "ANQP":
            return (g, _ANQP_IDX.get(norm_n,999), ch.name)
        if ch.group_key == "HTV":
            return (g, _HTV_IDX.get(norm_n, 999), ch.name)
        if ch.group_key == "VTVcab":
            return (g, _VTVcab_IDX.get(norm_n, 999), ch.name)
        if ch.group_key == "SCTV":
            return (g, _SCTV_IDX.get(norm_n, 999), ch.name)
        if ch.group_key == "LOCAL":
            return (g, ch.province_idx, ch.name)
        return (g, 0, ch.name)

    return sorted(channels, key=key)


def write_m3u(channels: list[Channel], path: str) -> None:
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(f'#EXTM3U url-tvg="{MY_EPG_URL}"\n')
            f.write(f'#EXTM3U x-tvg-url="{MY_EPG_URL}"\n')
            for src in SOURCES:
                f.write(f"#EXTM3U-SOURCE:{src}\n")
            for ch in channels:
                f.write(
                    f'#EXTINF:-1 tvg-id="{ch.tvg_id}" '
                    f'tvg-logo="{ch.tvg_logo}" '
                    f'group-title="{ch.group_label}",{ch.name}\n'
                    f"{ch.url}\n"
                )
        print(f"✅  Đã ghi {len(channels)} kênh → {path}")
    except IOError as e:
        print(f"❌  Lỗi ghi file {path}: {e}", file=sys.stderr)
        sys.exit(1)


# ──────────────────────────────────────────────────────────────────────
# XỬ LÝ FILE M3U THỦ CÔNG
# ──────────────────────────────────────────────────────────────────────
def update_manual_m3u(input_path: str, output_path: str) -> None:
    """Đọc file M3U thủ công, giữ nguyên tất cả kênh/thứ tự, chỉ chèn link EPG mới vào đầu."""
    print(f"\n📝 Đang cập nhật EPG cho file thủ công: {input_path}...")
    try:
        with open(input_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        # Lọc bỏ các dòng #EXTM3U cũ (nếu có)
        content_lines = [line for line in lines if not line.startswith("#EXTM3U")]

        # Ghi file mới với Header EPG cá nhân lên đầu
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(f'#EXTM3U url-tvg="{MY_EPG_URL}"\n')
            f.write(f'#EXTM3U x-tvg-url="{MY_EPG_URL}"\n')
            f.writelines(content_lines)

        print(f"✅ Đã tạo file M3U thủ công kèm EPG mới → {output_path}")
    except FileNotFoundError:
        print(f"  ⚠ Không tìm thấy file {input_path}, bỏ qua bước này.")
    except Exception as e:
        print(f"  ⚠ Lỗi xử lý file M3U thủ công: {e}", file=sys.stderr)


# ──────────────────────────────────────────────────────────────────────
# CẬP NHẬT MÚI GIỜ EPG
# ──────────────────────────────────────────────────────────────────────
def fix_epg_timezone(input_xml_url: str, output_xml_path: str = EPG_OUTPUT_FILE) -> None:
    print(f"\n⏳ Đang tải và sửa múi giờ EPG từ {input_xml_url}...")
    xml_text = fetch(input_xml_url)
    if not xml_text:
        print("  ⚠ Không thể tải file EPG XML")
        return

    try:
        root = ET.fromstring(xml_text)
        for prog in root.findall('programme'):
            for attr in ['start', 'stop']:
                val = prog.get(attr)
                if val:
                    clean_val = val.split()[0]
                    if len(clean_val) == 14:
                        prog.set(attr, f"{clean_val} +0700")

        tree = ET.ElementTree(root)
        tree.write(output_xml_path, encoding='utf-8', xml_declaration=True)
        print(f"✅ Đã xử lý và lưu EPG chuẩn giờ Việt Nam → {output_xml_path}")
    except Exception as e:
        print(f"  ⚠ Lỗi xử lý XML EPG: {e}", file=sys.stderr)


# ──────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────
def main() -> None:
    print(f"📡  EPG Target: {MY_EPG_URL}")
    
    # 1. Tải và xử lý EPG XML
    fix_epg_timezone(RAW_EPG_SOURCE, EPG_OUTPUT_FILE)
    
    # 2. Tải và xử lý danh sách kênh IPTV tự động
    processed: list[list[Channel]] = []
    for idx, src in enumerate(SOURCES, 1):
        print(f"\n[{idx}/{len(SOURCES)}] Tải: {src}")
        text = fetch(src)
        if not text or "#EXTM3U" not in text:
            print("  ⚠  Bỏ qua (không phải M3U hợp lệ)")
            continue
        parsed = parse_m3u(text)
        print(f"     Nhận diện {len(parsed)} kênh TV")
        if parsed:
            processed.append(parsed)

    if processed:
        # Gộp, lọc trùng và sắp xếp cho danh sách tự động
        print("\n🔀  Gộp & dedup danh sách tự động…")
        final = sort_channels(merge_sources(processed))
        # Xuất file M3U tự động
        write_m3u(final, OUTPUT_FILE)
    else:
        print("⚠  Không có nguồn tự động nào hợp lệ.", file=sys.stderr)

    # 3. Xử lý file M3U thủ công (Giữ nguyên danh sách/thứ tự, chỉ gắn EPG)
    # File gốc bạn sưu tập đặt trên repository là: my_list.m3u
    # File đầu ra để dùng trên ứng dụng TV là ghi đè lên file gốc: my_list.m3u
    update_manual_m3u("my_list.m3u", "my_list.m3u")


if __name__ == "__main__":
    main()
