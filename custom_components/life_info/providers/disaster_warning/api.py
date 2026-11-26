"""灾害预警 数据源接口与四类 payload 解析."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from aiohttp import ClientSession
from homeassistant.util import dt as dt_util

from ...api import LifeInfoError, async_request_json
from .const import (
    CAPQUAKE_BASE,
    CATEGORY_REPORT,
    CATEGORY_TSUNAMI,
    SCOPE_TO_CATEGORY,
)

class DisasterWarningApiError(LifeInfoError):
    """灾害预警数据源返回异常."""

def _first(data: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return value
    return None

def _float(value: Any) -> float | None:
    try:
        return float(str(value).strip()) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None

def _int(value: Any) -> int | None:
    try:
        return int(float(str(value).strip())) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None

def _bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes")

def iso_time(value: Any) -> str | None:
    """异构时间统一成 ISO：毫秒/秒时间戳与常见日期字符串都收口."""
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        stamp = float(value) / 1000 if float(value) > 1e11 else float(value)
        return datetime.fromtimestamp(
            stamp, tz=dt_util.DEFAULT_TIME_ZONE
        ).isoformat(timespec="seconds")
    text = str(value).strip()
    for fmt in ("%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M"):
        try:
            return datetime.strptime(text, fmt).replace(
                tzinfo=dt_util.DEFAULT_TIME_ZONE
            ).isoformat(timespec="seconds")
        except ValueError:
            continue
    return text

def _text(value: Any) -> str | None:
    """标量转展示文本：整数值的 float 去掉 .0，避免烈度显示成 1.0."""
    if value in (None, ""):
        return None
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)

def _record(
    schema: str,
    scope: str,
    raw: dict[str, Any],
    *,
    event_id: Any = None,
    location: Any = None,
    magnitude: Any = None,
    intensity: Any = None,
    time: Any = None,
    depth: Any = None,
    serial: Any = None,
    is_cancel: Any = None,
    level: Any = None,
    recv_time: Any = None,
) -> dict[str, Any] | None:
    """统一结构；无事件 ID 且无时间视为空 payload，返回 None 由上层忽略."""
    if not isinstance(raw, dict):
        return None
    event_id = str(event_id) if event_id not in (None, "") else ""
    parsed_time = iso_time(time)
    if not event_id and not parsed_time:
        return None
    return {
        "schema": schema,
        "scope": scope,
        "category": SCOPE_TO_CATEGORY.get(scope),
        "event_id": event_id or f"{scope}_{parsed_time or recv_time}",
        "location": _text(location),
        "magnitude": _float(magnitude),
        "intensity": _text(intensity),
        "time": parsed_time,
        "depth": _float(depth),
        "serial": _int(serial),
        "is_cancel": _bool(is_cancel),
        "level": _text(level),
        "recv_time": _int(recv_time),
        "source": "capquake",
        "raw": raw,
        "cache_at": None,
    }

def parse_cea(scope: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    """CEA/CEA-PR 及同类统一事件；字段缺失时按通用别名兜底."""
    return _record(
        "cea",
        scope,
        payload,
        event_id=_first(payload, "event_id", "EventID", "eventId", "identifier", "id"),
        location=_first(
            payload, "location", "epicenter_name", "epicenterPlace",
            "placeName", "Hypocenter",
        ),
        magnitude=_first(payload, "magnitude", "Magunitude", "M"),
        intensity=_first(payload, "max_intensity", "MaxIntensity", "intensity"),
        time=_first(payload, "OriginTime", "origin_time", "time", "originTime"),
        depth=_first(payload, "depth", "Depth"),
        serial=_first(payload, "serial", "Serial"),
        is_cancel=_first(payload, "is_cancel", "isCancel", "cancelled"),
        recv_time=_first(payload, "recv_time", "recvTime"),
    )

def parse_jma(scope: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    """JMA 紧急地震速报：保留上游 Magunitude 拼写."""
    return _record(
        "jma_eew",
        scope,
        payload,
        event_id=_first(payload, "EventID", "event_id"),
        location=_first(payload, "Hypocenter", "location"),
        magnitude=_first(payload, "Magunitude", "magnitude"),
        intensity=_first(payload, "MaxIntensity", "max_intensity"),
        time=_first(payload, "OriginTime", "origin_time"),
        depth=_first(payload, "Depth", "depth"),
        serial=_first(payload, "Serial", "serial"),
        is_cancel=_first(payload, "isCancel", "is_cancel"),
        recv_time=_first(payload, "recv_time", "recvTime"),
    )

def _time_value(value: Any) -> float:
    """把时间戳/日期串统一成可比数值，供挑最新一条."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    text = str(value or "").strip()
    if not text:
        return 0.0
    for fmt in ("%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M"):
        try:
            return datetime.strptime(text, fmt).timestamp()
        except ValueError:
            continue
    if (parsed := dt_util.parse_datetime(text)) is not None:
        return parsed.timestamp()
    try:
        return float(text)
    except ValueError:
        return 0.0

def _latest(rows: list[Any], *keys: str) -> dict[str, Any] | None:
    """按给定时间字段取最新一条；时间戳与日期串都支持."""
    items = [row for row in rows if isinstance(row, dict)]
    if not items:
        return None

    def sort_key(row: dict[str, Any]) -> float:
        for name in keys:
            if (value := _time_value(row.get(name))) > 0:
                return value
        return 0.0

    return max(items, key=sort_key)

def parse_tsunami(scope: str, payload: Any) -> dict[str, Any] | None:
    """海啸 CAP 报文：items[] 取最新，用报文 id 作事件身份."""
    rows = payload.get("items") if isinstance(payload, dict) else payload
    item = _latest(rows or [], "recv_time", "time_ts", "time")
    if item is None:
        return None
    areas = item.get("areas") or []
    area_name = ""
    if areas and isinstance(areas[0], dict):
        area_name = str(areas[0].get("name") or "")
    raw_area = item.get("area")
    location = (
        str(raw_area)
        if isinstance(raw_area, str) and raw_area
        else area_name or _first(item, "region", "title") or None
    )
    return _record(
        "tsunami",
        scope,
        item,
        event_id=_first(item, "id", "event_id"),
        location=location,
        time=_first(item, "time", "report_time", "update_time"),
        is_cancel=_first(item, "cancelled", "cancel"),
        level=_first(item, "level_name", "level_text", "level"),
        recv_time=_first(item, "recv_time", "update_ts", "alarm_ts", "time_ts"),
    )

def parse_report(scope: str, payload: Any) -> dict[str, Any] | None:
    """地震报告信封：Data / items[] / cenc No* / 裸对象 四种形态收口."""
    if isinstance(payload, list):
        item = _latest(payload, "recvTime", "originTime")
        return _report_record(scope, item) if item else None
    if not isinstance(payload, dict):
        return None

    if isinstance(payload.get("Data"), dict):
        data = payload["Data"]
        record = _report_record(scope, data, raw=payload)
        if record and payload.get("md5"):
            record["event_id"] = record["event_id"] or str(payload["md5"])
        return record

    if isinstance(payload.get("items"), list):
        item = _latest(payload["items"], "report_time_ts", "recv_time", "report_time")
        return _report_record(scope, item) if item else None

    # cenc：No1..NoN 字典 + 顶层 md5 包校验值，只取条目字典.
    if "No1" in payload or (
        payload and all(isinstance(value, dict) for value in payload.values())
    ):
        item = _latest(
            [value for value in payload.values() if isinstance(value, dict)],
            "ReportTime",
            "time",
            "recv_time",
        )
        return _report_record(scope, item) if item else None

    return _report_record(scope, payload)

def _intensity_value(item: dict[str, Any]) -> Any:
    """烈度归一：cwa_report 的 intensity 是分区分站嵌套结构，取最大分区值."""
    value = _first(item, "max_intensity", "intensity", "MaxIntensity")
    if isinstance(value, dict):
        areas = value.get("area") or []
        numbers = [
            _float(area.get("maxIntensity"))
            for area in areas
            if isinstance(area, dict)
        ]
        numbers = [number for number in numbers if number is not None]
        return max(numbers) if numbers else None
    if isinstance(value, list):
        numbers = [
            _float(entry.get("max_intensity") or entry.get("maxInt"))
            for entry in value
            if isinstance(entry, dict)
        ]
        numbers = [number for number in numbers if number is not None]
        return max(numbers) if numbers else None
    return value

def _report_record(
    scope: str, item: dict[str, Any], *, raw: dict[str, Any] | None = None
) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    payload = raw if raw is not None else item
    return _record(
        "report",
        scope,
        payload,
        event_id=_first(item, "id", "EventID", "event_id", "md5"),
        location=_first(item, "location", "placeName", "epicenterPlace", "title")
        or (
            (item.get("hypocenter") or {}).get("name")
            if isinstance(item.get("hypocenter"), dict)
            else None
        ),
        magnitude=_first(item, "magnitude", "Magunitude"),
        intensity=_intensity_value(item),
        time=_first(item, "OriginTime", "origin_time", "time", "originTime"),
        depth=_first(item, "depth", "Depth"),
        serial=_first(item, "serial", "Serial"),
        is_cancel=_first(item, "is_cancel", "isCancel", "cancelled"),
        recv_time=_first(item, "recv_time", "recvTime"),
    )

def parse_payload(scope: str, payload: Any) -> dict[str, Any] | None:
    """按 scope 归类别派发解析器；解析失败只丢本条，不抛给调用方."""
    if not payload:
        return None
    category = SCOPE_TO_CATEGORY.get(scope)
    try:
        if category == CATEGORY_TSUNAMI:
            return parse_tsunami(scope, payload)
        if scope == "jma_eew":
            return parse_jma(scope, payload)
        if category == CATEGORY_REPORT:
            return parse_report(scope, payload)
        if isinstance(payload, dict):
            return parse_cea(scope, payload)
    except (TypeError, ValueError, KeyError, AttributeError) as err:
        raise DisasterWarningApiError(f"{scope} 解析失败: {err}") from err
    return None

def freshness_key(record: dict[str, Any]) -> float:
    """新旧判定：优先服务端接收时刻，秒级统一换算为毫秒."""
    if (recv := record.get("recv_time")) is not None:
        value = float(recv)
        return value * 1000 if value < 1e11 else value
    if (text := record.get("time")):
        if (parsed := dt_util.parse_datetime(str(text))) is not None:
            return parsed.timestamp() * 1000
    return 0.0

def record_md5(record: dict[str, Any]) -> str | None:
    """报告同份判定：信封顶层或 cenc 条目内的 md5."""
    raw = record.get("raw")
    if isinstance(raw, dict) and raw.get("md5"):
        return str(raw["md5"])
    return None

_NORMALIZED_ATTRS: tuple[str, ...] = (
    "schema",
    "scope",
    "category",
    "event_id",
    "location",
    "magnitude",
    "intensity",
    "time",
    "depth",
    "serial",
    "is_cancel",
    "level",
    "recv_time",
    "source",
)

def _attr_key(name: str) -> str:
    """属性键归一为 hassfest 接受的 [a-z0-9-_]（原文键名仍留 raw 整包）."""
    key = re.sub(r"[^a-z0-9_-]+", "_", str(name).lower()).strip("-_")
    return key

def record_attributes(record: dict[str, Any]) -> dict[str, Any]:
    """Sensor 属性：归一字段打底 + payload 全量平铺；同名同值跳过，同名异值加 raw_ 前缀."""
    attrs: dict[str, Any] = {
        name: record[name]
        for name in _NORMALIZED_ATTRS
        if record.get(name) is not None
    }

    raw = record.get("raw")
    flat = dict(raw) if isinstance(raw, dict) else {}
    if isinstance(flat.get("Data"), dict):
        data = flat.pop("Data")
        flat = {**data, **flat}  # 报告信封解包；外层字段优先

    for name, value in flat.items():
        if value is None:
            continue
        key = _attr_key(name)
        if not key:
            continue
        if key in attrs:
            if attrs[key] == value:
                continue  # 同键同值：归一字段已承载，原文仍在 raw 整包内
            key = f"raw_{key}"
        attrs[key] = value

    if isinstance(raw, dict):
        attrs["raw"] = raw  # 整包保留，覆盖同名的原文字段
    return attrs

async def async_fetch_snapshot(session: ClientSession) -> dict[str, Any]:
    """全源快照：按 scope 分组对象，缺数据的源不会出现."""
    payload = await async_request_json(
        session, "GET", f"{CAPQUAKE_BASE}/snapshot"
    )
    if not isinstance(payload, dict):
        raise DisasterWarningApiError("snapshot 响应非对象")
    return payload

async def async_fetch_scope(session: ClientSession, scope: str) -> Any:
    """单源最新一条；503 no data yet 视为暂无数据."""
    return await async_request_json(
        session, "GET", f"{CAPQUAKE_BASE}/{scope}"
    )