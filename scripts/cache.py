"""
cache — 数据缓存系统（P3-2）

按分类缓存 API 响应数据，TTL 过期后自动失效。
存储格式：JSON 文件，按 category 存子目录，key 用 md5(code+category) 生成。
cache 目录自动创建（如不存在）。
"""

import os
import json
import hashlib
from typing import Optional, Any

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cache")

CACHE_TTL = {
    "kline": 7200,      # K线: 2小时
    "finance": 86400,   # 财务: 24小时
    "peers": 604800,    # 同行: 7天
    "news": 3600,       # 新闻: 1小时
    "market": 3600,     # 市场指数: 1小时
}

DEFAULT_TTL = 3600  # 默认1小时


def _key_hash(code: str, category: str) -> str:
    """用 md5(code+category) 生成缓存 key。"""
    return hashlib.md5((str(code) + category).encode("utf-8")).hexdigest()


def _ensure_cache_dir(category: str) -> str:
    """确保分类缓存目录存在并返回路径。"""
    cat_dir = os.path.join(CACHE_DIR, category)
    os.makedirs(cat_dir, exist_ok=True)
    return cat_dir


def cache_get(key: str, ttl_seconds: Optional[int] = None) -> Optional[dict]:
    """
    读取缓存。返回 dict 数据，过期或不存在返回 None。

    参数：
        key — 缓存 key（通常是股票代码或唯一标识）
        ttl_seconds — 可选，覆盖分类默认 TTL
    """
    for category, default_ttl in CACHE_TTL.items():
        cat_dir = os.path.join(CACHE_DIR, category)
        if not os.path.isdir(cat_dir):
            continue
        h = _key_hash(key, category)
        path = os.path.join(cat_dir, f"{h}.json")
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError):
            continue

        ts = data.get("_ts", 0)
        ttl = ttl_seconds if ttl_seconds is not None else default_ttl
        import time
        if time.time() - ts > ttl:
            # 缓存过期，清理
            try:
                os.remove(path)
            except OSError:
                pass
            return None
        return data.get("data")

    return None


def cache_set(key: str, data: Any, ttl_seconds: Optional[int] = None) -> None:
    """
    写入缓存。

    参数：
        key — 缓存 key
        data — 任意可 JSON 序列化的数据
        ttl_seconds — 可选，覆盖分类默认 TTL
    """
    # 找到匹配的分类
    category = None
    for cat, default_ttl in CACHE_TTL.items():
        if ttl_seconds is None or ttl_seconds == default_ttl:
            category = cat
            break
    if category is None:
        category = "default"

    # 用 TTL 反向查找分类
    if ttl_seconds is not None:
        for cat, default_ttl in CACHE_TTL.items():
            if ttl_seconds == default_ttl:
                category = cat
                break
        else:
            category = "custom"

    cat_dir = _ensure_cache_dir(category)
    h = _key_hash(key, category)
    path = os.path.join(cat_dir, f"{h}.json")

    import time
    payload = {"_ts": time.time(), "data": data}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)


def cache_set_with_category(key: str, category: str, data: Any) -> None:
    """
    写入缓存（显式指定分类）。

    参数：
        key — 缓存 key
        category — 分类名（如 "kline", "finance", "peers", "news", "market"）
        data — 任意可 JSON 序列化的数据
    """
    cat_dir = _ensure_cache_dir(category)
    h = _key_hash(key, category)
    path = os.path.join(cat_dir, f"{h}.json")
    import time
    payload = {"_ts": time.time(), "data": data}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)


def cache_clear(category: Optional[str] = None) -> None:
    """
    清除缓存。

    参数：
        category — 为空则清除所有分类缓存；指定则清除单个分类。
    """
    import shutil
    if category:
        cat_dir = os.path.join(CACHE_DIR, category)
        if os.path.isdir(cat_dir):
            shutil.rmtree(cat_dir)
            os.makedirs(cat_dir, exist_ok=True)
    else:
        if os.path.isdir(CACHE_DIR):
            for d in os.listdir(CACHE_DIR):
                full = os.path.join(CACHE_DIR, d)
                if os.path.isdir(full):
                    shutil.rmtree(full)
                    os.makedirs(full, exist_ok=True)
