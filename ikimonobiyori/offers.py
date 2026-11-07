"""答えの末尾の案内(提案)の一覧と、写真つきページの対応テーマ(段階57 第1部。本人の指摘 2026-11-07: できないことを提案しない)。

案内の文は data/ask/offers.yaml の一覧から、条件を満たすものだけをコードが組み立てる。通信しない・書き込まない。"""
from pathlib import Path

import yaml

from .paths import DATA_FILES_DIR

OFFERS_PATH = DATA_FILES_DIR / "ask" / "offers.yaml"


def load(path=None):
    return yaml.safe_load(Path(path or OFFERS_PATH).read_text(encoding="utf-8"))


def theme_list(doc=None):
    return "、".join((doc or load())["page_support"]["labels"])


def unsupported_theme_message(doc=None):
    doc = doc or load()
    return doc["messages"]["unsupported_theme"].format(themes=theme_list(doc))


def guide_themes_supported(themes, doc=None):
    """guide page: 語から決まったガイドのテーマが、すべて対応済みか。"""
    return bool(themes) and set(themes) <= set((doc or load())["page_support"]["guide_themes"])


def ask_subjects_supported(subjects, doc=None):
    """ask page: facts の対象が、すべて対応済みか。"""
    return bool(subjects) and set(subjects) <= set((doc or load())["page_support"]["ask_subjects"])


def available(conditions, doc=None):
    """conditions: 条件の名前 → 真偽。すべて真の案内だけ → [{id, text}]。"""
    doc = doc or load()
    return [{"id": o["id"], "text": o["text"]} for o in doc["offers"] if all(conditions.get(k) for k in o["requires"])]


def texts(offers):
    return [o["text"] for o in offers or []]


def all_texts(doc=None):
    return [o["text"] for o in (doc or load())["offers"]]


def unsupported_reply(what, offers_now=(), doc=None):
    """頼まれたことが今できないとき: 1 行の案内と、確実にできる別のこと(条件を満たす案内)だけ。"""
    doc = doc or load()
    return [doc["messages"]["unsupported_reply"].format(what=what)] + list(texts(offers_now))[:1]
