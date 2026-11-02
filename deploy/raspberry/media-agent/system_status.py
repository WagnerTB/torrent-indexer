import glob
import json
import os
import shutil
import socket
import threading
import time
from datetime import datetime, timezone

STATUS_PROBE_FILE = os.getenv("STATUS_PROBE_FILE", "/state/pi-status.json").strip()
STATUS_CLEAR_FILE = os.getenv("STATUS_CLEAR_FILE", STATUS_PROBE_FILE + ".clear").strip()
PROBE_MAX_AGE = 120
CPU_SAMPLE_INTERVAL = 2.0
THROTTLE_EVENT_MASK = (1 << 16) | (1 << 17) | (1 << 18) | (1 << 19)


def _now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _read_text(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read().strip()
    except OSError:
        return ""


def _format_bytes(value):
    try:
        size = float(value or 0)
    except (TypeError, ValueError):
        size = 0.0
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            if unit in ("B", "KB", "MB"):
                return f"{size:.0f} {unit}"
            text = f"{size:.1f}".rstrip("0").rstrip(".")
            return f"{text or '0'} {unit}"
        size /= 1024
    return "0 B"


def _format_duration(seconds):
    try:
        total = int(max(0, float(seconds)))
    except (TypeError, ValueError):
        total = 0
    days, remainder = divmod(total, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes = remainder // 60
    if days:
        return f"{days}d {hours}h {minutes}m"
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m"
    return f"{total}s"


def _cpu_times():
    with open("/proc/stat", encoding="utf-8") as handle:
        parts = handle.readline().split()
    if not parts or parts[0] != "cpu":
        raise ValueError("/proc/stat sem linha cpu")
    values = [int(value) for value in parts[1:]]
    idle = values[3] + (values[4] if len(values) > 4 else 0)
    return idle, sum(values)


class _CpuSampler:
    def __init__(self):
        self._lock = threading.Lock()
        self._percent = None
        self._previous = None
        self._started = False

    def start(self):
        with self._lock:
            if self._started:
                return
        previous = _cpu_times()
        with self._lock:
            if self._started:
                return
            self._started = True
            self._previous = previous
        thread = threading.Thread(target=self._run, name="pi-cpu-sampler", daemon=True)
        thread.start()

    def _run(self):
        while True:
            time.sleep(CPU_SAMPLE_INTERVAL)
            try:
                self.sample()
            except Exception:
                pass

    def sample(self):
        current = _cpu_times()
        with self._lock:
            previous = self._previous
            self._previous = current
            if previous is None:
                return self._percent
            total_delta = current[1] - previous[1]
            idle_delta = current[0] - previous[0]
            if total_delta <= 0:
                return self._percent
            percent = (1.0 - idle_delta / total_delta) * 100.0
            self._percent = round(max(0.0, min(100.0, percent)), 1)
            return self._percent

    def value(self, wait=0.0):
        self.start()
        with self._lock:
            current = self._percent
        if current is None and wait > 0:
            time.sleep(wait)
            try:
                self.sample()
            except Exception:
                pass
            with self._lock:
                current = self._percent
        return current


_CPU_SAMPLER = _CpuSampler()


def _load_payload():
    try:
        load1, load5, load15 = os.getloadavg()
    except (AttributeError, OSError):
        load1 = load5 = load15 = 0.0
    return {
        "load1": round(load1, 2),
        "load5": round(load5, 2),
        "load15": round(load15, 2),
    }


def _cpu_payload():
    payload = {
        "percent": _CPU_SAMPLER.value(wait=0.2),
        "cores": os.cpu_count() or 0,
    }
    payload.update(_load_payload())
    return payload


def _memory_payload():
    values = {}
    with open("/proc/meminfo", encoding="utf-8") as handle:
        for line in handle:
            key, _, rest = line.partition(":")
            if not rest:
                continue
            try:
                values[key] = int(rest.strip().split()[0])
            except (ValueError, IndexError):
                continue
    total = int(values.get("MemTotal", 0)) * 1024
    available = values.get("MemAvailable")
    if available is None:
        available = (
            values.get("MemFree", 0)
            + values.get("Buffers", 0)
            + values.get("Cached", 0)
        )
    available = int(available) * 1024
    used = max(0, total - available)
    percent = round(used / total * 100) if total else 0
    swap_total = int(values.get("SwapTotal", 0)) * 1024
    swap_free = int(values.get("SwapFree", 0)) * 1024
    swap_used = max(0, swap_total - swap_free)
    swap_percent = round(swap_used / swap_total * 100) if swap_total else 0
    return {
        "total": total,
        "used": used,
        "available": available,
        "percent": percent,
        "totalLabel": _format_bytes(total),
        "usedLabel": _format_bytes(used),
        "availableLabel": _format_bytes(available),
        "swapTotal": swap_total,
        "swapUsed": swap_used,
        "swapPercent": swap_percent,
        "swapTotalLabel": _format_bytes(swap_total),
        "swapUsedLabel": _format_bytes(swap_used),
    }


def _temperature_payload():
    preferred = {
        "cpu-thermal",
        "soc-thermal",
        "cpu_thermal",
        "soc_thermal",
        "x86_pkg_temp",
    }
    fallback = None
    for zone in sorted(glob.glob("/sys/class/thermal/thermal_zone*")):
        raw = _read_text(os.path.join(zone, "temp"))
        if not raw:
            continue
        try:
            value = float(raw)
        except ValueError:
            continue
        celsius = value / 1000.0 if abs(value) > 200 else value
        kind = _read_text(os.path.join(zone, "type")).lower()
        item = {
            "celsius": round(celsius, 1),
            "label": f"{celsius:.1f} °C",
            "source": kind or os.path.basename(zone),
        }
        if kind in preferred:
            return item
        if fallback is None:
            fallback = item
    return fallback


def _probe_payload():
    if not STATUS_PROBE_FILE:
        return {}
    try:
        with open(STATUS_PROBE_FILE, encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict):
            return {}
        age = max(0.0, time.time() - os.stat(STATUS_PROBE_FILE).st_mtime)
        result = dict(payload)
        result["ageSeconds"] = round(age, 1)
        result["stale"] = age > PROBE_MAX_AGE
        return result
    except (OSError, ValueError, TypeError):
        return {}


def _as_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value):
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    text = str(value or "").strip()
    if not text:
        return None
    try:
        if text.lower().startswith("0x"):
            return int(text, 16)
        return int(text, 10)
    except ValueError:
        return None


def _throttle_flags(value):
    if value is None:
        return None
    return {
        "undervoltage": bool(value & (1 << 0)),
        "frequencyCapped": bool(value & (1 << 1)),
        "throttled": bool(value & (1 << 2)),
        "softTempLimit": bool(value & (1 << 3)),
        "undervoltageOccurred": bool(value & (1 << 16)),
        "frequencyCappedOccurred": bool(value & (1 << 17)),
        "throttledOccurred": bool(value & (1 << 18)),
        "softTempLimitOccurred": bool(value & (1 << 19)),
    }


def _voltage_payload(probe):
    core = _as_float(probe.get("coreVolts"))
    if core is None:
        core = _as_float(probe.get("core_volts"))
    throttled = _as_int(probe.get("throttled"))
    pending = _as_int(probe.get("pendingThrottled"))
    if pending is None:
        pending = (throttled or 0) & THROTTLE_EVENT_MASK
    recent = _as_int(probe.get("recentThrottled"))
    stale = bool(probe.get("stale"))
    live = _throttle_flags(throttled) or {}
    pending_flags = _throttle_flags(pending) or {}
    current_flags = {
        "undervoltage": bool(live.get("undervoltage")),
        "frequencyCapped": bool(live.get("frequencyCapped")),
        "throttled": bool(live.get("throttled")),
        "softTempLimit": bool(live.get("softTempLimit")),
    }
    pending_event_flags = {
        "undervoltageOccurred": bool(pending_flags.get("undervoltageOccurred")),
        "frequencyCappedOccurred": bool(pending_flags.get("frequencyCappedOccurred")),
        "throttledOccurred": bool(pending_flags.get("throttledOccurred")),
        "softTempLimitOccurred": bool(pending_flags.get("softTempLimitOccurred")),
    }
    flags = dict(current_flags)
    flags.update(pending_event_flags)
    if throttled is None:
        status = "unknown"
        label = "N/D"
    elif stale:
        status = "unknown"
        label = "N/D"
    elif current_flags["undervoltage"] or current_flags["throttled"]:
        status = "critical"
        label = "Subtensão" if current_flags["undervoltage"] else "Throttling"
    elif pending_event_flags["undervoltageOccurred"] or pending_event_flags["throttledOccurred"]:
        status = "critical"
        label = "Subtensão" if pending_event_flags["undervoltageOccurred"] else "Throttling"
    elif (
        current_flags["frequencyCapped"]
        or current_flags["softTempLimit"]
        or pending_event_flags["frequencyCappedOccurred"]
        or pending_event_flags["softTempLimitOccurred"]
    ):
        status = "warning"
        label = "Atenção"
    else:
        status = "ok"
        label = "OK"
    return {
        "core": core,
        "coreLabel": f"{core:.2f} V" if core is not None else "—",
        "throttled": throttled,
        "throttledHex": f"0x{throttled:X}" if throttled is not None else None,
        "pending": pending,
        "pendingHex": f"0x{pending:X}" if pending is not None else None,
        "historyHex": f"0x{throttled:X}" if throttled is not None else None,
        "recent": recent,
        "recentHex": f"0x{recent:X}" if recent is not None else None,
        "stale": stale,
        "status": status,
        "statusLabel": label,
        "flags": flags,
        "currentFlags": current_flags,
        "pendingFlags": pending_event_flags,
    }


def _host_payload():
    return {
        "hostname": _read_text("/host/root-probe") or socket.gethostname(),
        "model": _read_text("/sys/firmware/devicetree/base/model").replace("\x00", "").strip(),
        "kernel": os.uname().release,
    }


def _uptime_payload():
    raw = _read_text("/proc/uptime")
    seconds = _as_float(raw.split()[0]) if raw else 0.0
    seconds = seconds or 0.0
    return {
        "seconds": int(seconds),
        "label": _format_duration(seconds),
    }


def _storage_entries(storage_config):
    if not storage_config:
        return []
    try:
        data = json.loads(storage_config)
    except (TypeError, ValueError):
        return []
    return data if isinstance(data, list) else []


def storage_payload(storage_config):
    items = []
    for entry in _storage_entries(storage_config):
        if not isinstance(entry, dict):
            continue
        parts = []
        for part in entry.get("parts") or []:
            if not isinstance(part, dict):
                continue
            path = str(part.get("path") or "").strip()
            if not path:
                continue
            try:
                usage = shutil.disk_usage(path)
            except OSError:
                continue
            total = int(usage.total)
            used = int(usage.used)
            free = int(usage.free)
            parts.append(
                {
                    "label": str(part.get("label") or path),
                    "total": total,
                    "used": used,
                    "free": free,
                    "percent": round(used / total * 100) if total else 0,
                    "totalLabel": _format_bytes(total),
                    "usedLabel": _format_bytes(used),
                    "freeLabel": _format_bytes(free),
                }
            )
        if not parts:
            continue
        total = sum(part["total"] for part in parts)
        used = sum(part["used"] for part in parts)
        free = sum(part["free"] for part in parts)
        items.append(
            {
                "id": str(entry.get("id") or entry.get("label") or "storage"),
                "label": str(entry.get("label") or "Armazenamento"),
                "kind": str(entry.get("kind") or ""),
                "total": total,
                "used": used,
                "free": free,
                "percent": round(used / total * 100) if total else 0,
                "totalLabel": _format_bytes(total),
                "usedLabel": _format_bytes(used),
                "freeLabel": _format_bytes(free),
                "parts": parts,
            }
        )
    return {"ok": True, "items": items, "generatedAt": _now_iso()}


def status_payload(storage_config):
    errors = []

    def collect(name, fn, default):
        try:
            return fn()
        except Exception as error:
            errors.append(f"{name}: {error}")
            return default

    probe = _probe_payload()
    cpu = collect("cpu", _cpu_payload, {"percent": None, "cores": 0})
    memory = collect("memory", _memory_payload, None)
    temperature = collect("temperature", _temperature_payload, None)
    voltage = collect(
        "voltage",
        lambda: _voltage_payload(probe),
        {"core": None, "coreLabel": "—", "throttled": None, "throttledHex": None,
         "pending": None, "pendingHex": None, "historyHex": None,
         "recent": None, "recentHex": None,
         "stale": False, "status": "unknown", "statusLabel": "N/D",
         "flags": {}, "currentFlags": {}, "pendingFlags": {}},
    )
    if temperature is None:
        probe_temp = _as_float(probe.get("temperature"))
        if probe_temp is not None:
            temperature = {
                "celsius": round(probe_temp, 1),
                "label": f"{probe_temp:.1f} °C",
                "source": "probe",
            }
    if temperature is not None:
        celsius = temperature["celsius"]
        if celsius >= 80:
            temperature["status"] = "critical"
            temperature["statusLabel"] = "Crítico"
        elif celsius >= 70:
            temperature["status"] = "warning"
            temperature["statusLabel"] = "Atenção"
        else:
            temperature["status"] = "ok"
            temperature["statusLabel"] = "OK"
    return {
        "ok": True,
        "generatedAt": _now_iso(),
        "host": collect("host", _host_payload, {}),
        "uptime": collect("uptime", _uptime_payload, {"seconds": 0, "label": "—"}),
        "cpu": cpu,
        "memory": memory,
        "temperature": temperature,
        "voltage": voltage,
        "storage": collect("storage", lambda: storage_payload(storage_config), {"ok": False, "items": []}),
        "errors": errors,
    }


def request_throttle_clear(storage_config, timeout=6.0):
    payload = status_payload(storage_config)
    voltage = payload.get("voltage") or {}
    current = voltage.get("currentFlags") or {}
    if current.get("undervoltage") or current.get("throttled"):
        payload["cleared"] = False
        payload["error"] = "há subtensão/throttling ativo; aguarde normalizar"
        return payload
    pending = _as_int(voltage.get("pending"))
    if pending is not None and (pending & THROTTLE_EVENT_MASK) == 0:
        payload["cleared"] = True
        return payload
    if not STATUS_CLEAR_FILE:
        payload["cleared"] = False
        payload["error"] = "caminho de limpeza não configurado"
        return payload
    try:
        with open(STATUS_CLEAR_FILE, "w", encoding="utf-8") as handle:
            handle.write(_now_iso())
    except OSError as error:
        payload["cleared"] = False
        payload["error"] = f"não foi possível solicitar limpeza: {error}"
        return payload
    deadline = time.time() + max(1.0, float(timeout))
    try:
        while time.time() < deadline:
            time.sleep(0.25)
            probe = _probe_payload()
            current_pending = _as_int(probe.get("pendingThrottled"))
            if current_pending is not None and (current_pending & THROTTLE_EVENT_MASK) == 0:
                break
    finally:
        try:
            os.remove(STATUS_CLEAR_FILE)
        except OSError:
            pass
    payload = status_payload(storage_config)
    voltage = payload.get("voltage") or {}
    pending = _as_int(voltage.get("pending"))
    payload["cleared"] = bool(pending is not None and (pending & THROTTLE_EVENT_MASK) == 0)
    if not payload["cleared"]:
        payload["error"] = "o probe ainda não confirmou a limpeza; tente novamente em instantes"
    return payload
