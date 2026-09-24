"""One page that answers "is it actually working right now?".

Checking the stack meant reading four logs and poking three ports. This serves
a single local page that says, in plain words, whether the robot is connected,
whether the microphone is reaching the model, whether the camera is available,
and how long the last few replies took.

The freshness numbers carry the page. "Last heard 4 seconds ago" and "last heard
9 minutes ago" are the difference between a live demo and a dead one, so they are
the largest thing on the screen and they turn red by themselves. Everything else
is there to explain a red one.

    .venv\\Scripts\\python.exe tools\\status_board.py        ->  http://127.0.0.1:8770
"""

import re
import json
import time
import argparse
import subprocess
import urllib.request
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple
from pathlib import Path
from datetime import datetime
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

try:
    import psutil
except ImportError:  # still works outside the venv, just via netstat
    psutil = None

ROOT = Path(r"D:\海风")
RUNTIME = ROOT / ".runtime"
DAEMON_PORT = 8000
DAEMON = f"http://127.0.0.1:{DAEMON_PORT}"
REALTIME_PORT = 8765
APP_PORT = 7860
DIARY_PORT = 8800

FRESH = 60.0    # seconds: still mid-conversation
STALE = 300.0   # seconds: long enough that something is probably wrong

SNAP_TTL = 1.2   # the page polls every 3s, and every open tab polls separately
PORTS_TTL = 4.0

STAMP = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")
HEARD = re.compile(r"heard: (.*)$")
REPLY = re.compile(r"reply: (.*)$")
TIMING = re.compile(r"timing: model ([\d.]+)s\s+speech ([\d.]+)s")

_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
_CACHE: Dict[str, Tuple[float, Any]] = {"ports": (0.0, set()), "snap": (0.0, None)}


def _get(url: str, timeout: float = 1.5) -> Optional[Any]:
    """Fetch JSON, bypassing the machine's proxy for loopback.

    The timeout is short on purpose: a wedged daemon must not hold up the page.
    """
    try:
        with _OPENER.open(url, timeout=timeout) as response:
            return json.loads(response.read().decode() or "null")
    except Exception:
        return None


def _scan_ports() -> Set[int]:
    """Every local TCP port with a listener, without opening any connection."""
    if psutil is not None:
        try:
            return {c.laddr.port for c in psutil.net_connections(kind="tcp")
                    if c.status == psutil.CONN_LISTEN}
        except Exception:
            pass
    try:
        out = subprocess.run(["netstat", "-ano", "-p", "TCP"], check=False,
                             capture_output=True, text=True, timeout=8).stdout
    except Exception:
        return set()
    ports: Set[int] = set()
    for line in out.splitlines():
        parts = line.split()
        if len(parts) > 3 and parts[3] == "LISTENING":
            try:
                ports.add(int(parts[1].rsplit(":", 1)[-1]))
            except ValueError:
                pass
    return ports


def _listening(port: int) -> bool:
    """Is anyone listening on this port, from a table read a few seconds ago.

    One Get-NetTCPConnection per port cost two seconds, which a three-second
    poll cannot afford; reading the whole table once and caching it is instant.
    A plain TCP connect would be cheaper still, but knocking on the realtime
    server every three seconds would fill the very log this page reads.
    """
    stamp, ports = _CACHE["ports"]
    if time.time() - stamp >= PORTS_TTL:
        ports = _scan_ports()
        _CACHE["ports"] = (time.time(), ports)
    return port in ports


def _tail(path: Path, limit: int = 4000) -> List[str]:
    try:
        with path.open("rb") as handle:
            handle.seek(0, 2)
            handle.seek(max(0, handle.tell() - 300_000))
            return handle.read().decode("utf-8", errors="replace").splitlines()[-limit:]
    except OSError:
        return []


def _gap(when: Optional[float]) -> Optional[float]:
    """Seconds since a timestamp, or None if it never happened."""
    return None if when is None else max(0.0, time.time() - when)


def _span(gap: Optional[float]) -> str:
    if gap is None:
        return "从未"
    if gap < 60:
        return f"{gap:.0f} 秒"
    if gap < 3600:
        return f"{gap / 60:.0f} 分钟"
    return f"{gap / 3600:.1f} 小时"


def _ago(gap: Optional[float]) -> str:
    return "从未" if gap is None else _span(gap) + "前"


def _when(line: str) -> Optional[float]:
    match = STAMP.match(line)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S").timestamp()
    except ValueError:
        return None


def _voice_log() -> List[str]:
    """The realtime log rotates on restart, so read across the seam.

    Otherwise every restart makes the conversation that just happened look as
    if it never did, and the page cries wolf.
    """
    return _tail(RUNTIME / "realtime.prev.log", 600) + \
        _tail(RUNTIME / "realtime.stderr.log", 4000)


def voice_state() -> Dict[str, Any]:
    """What the realtime server has been doing lately."""
    model = None
    heard: Optional[Tuple[Optional[float], str]] = None
    reply: Optional[Tuple[Optional[float], str]] = None
    pending: Optional[str] = None
    turns: List[Dict[str, Any]] = []
    for line in _voice_log():
        if "stt ready:" in line:
            model = line.split("stt ready:", 1)[1].strip()
        found = HEARD.search(line)
        if found:
            heard = (_when(line), found.group(1).strip()[:200])
            pending = heard[1]
            continue
        found = REPLY.search(line)
        if found:
            reply = (_when(line), found.group(1).strip()[:200])
            turns.append({"at": reply[0], "heard": pending or "",
                          "reply": reply[1], "model": None, "speech": None})
            pending = None
            continue
        found = TIMING.search(line)
        if found and turns:
            turns[-1]["model"] = float(found.group(1))
            turns[-1]["speech"] = float(found.group(2))

    recent = turns[-6:]
    totals = sorted(t["model"] + t["speech"] for t in recent
                    if t["model"] is not None and t["speech"] is not None)
    return {
        "up": _listening(REALTIME_PORT),
        "app_up": _listening(APP_PORT),
        "stt": model,
        "turns_seen": len(turns),
        "heard_ago": _gap(heard[0] if heard else None),
        "reply_ago": _gap(reply[0] if reply else None),
        "heard_text": heard[1] if heard else "",
        "reply_text": reply[1] if reply else "",
        "turns": recent,
        "median": round(totals[len(totals) // 2], 1) if totals else None,
    }


def _photos() -> List[float]:
    """Modification times of the glasses snapshots, oldest first."""
    times = []
    for path in (RUNTIME / "glasses").glob("*.jpg"):
        try:
            times.append(path.stat().st_mtime)
        except OSError:
            pass
    return sorted(times)


def verdict(data: Dict[str, Any]) -> Dict[str, Any]:
    """One honest line, assembled from the parts rather than declared."""
    robot, voice, cam = data["robot"], data["voice"], data["camera"]
    bad: List[str] = []
    warn: List[str] = []

    if robot["desktop_client"]:
        bad.append("官方桌面客户端已接管机器人，这套程序拿不到它")
    if not robot["up"]:
        bad.append(f"机器人 daemon 卡住了（{DAEMON_PORT} 端口在听但不回应）" if robot["serving"]
                   else f"机器人 daemon 没在跑（{DAEMON_PORT} 端口没人监听）")
    elif robot["error"]:
        bad.append(f"机器人报错：{robot['error']}")
    elif robot["state"] != "running":
        bad.append(f"机器人状态是 {robot['state'] or '未知'}，不是 running")
    elif robot["motors"] != "enabled":
        warn.append(f"电机 {robot['motors'] or '未知'}，机器人不会动")

    if not voice["up"]:
        bad.append(f"语音服务端离线（{REALTIME_PORT} 端口），说话不会有任何反应")
    if not voice["app_up"]:
        bad.append(f"对话应用离线（{APP_PORT} 端口）")
    if voice["up"] and not voice["stt"]:
        warn.append("日志里没有转写模型，语音链路可能还没起完")

    gap = voice["heard_ago"]
    if voice["up"]:
        if gap is None:
            warn.append("日志里还没有任何人说过话")
        elif gap > STALE:
            bad.append(f"已经 {_span(gap)}没听到有人说话")
        elif gap > FRESH:
            warn.append(f"{_span(gap)}没听到有人说话")

    if robot["up"]:
        if robot["hz"] is not None and robot["hz"] < 20:
            warn.append(f"控制环只有 {robot['hz']} Hz")
        if robot["errors"]:
            warn.append(f"控制环累计 {robot['errors']} 次错误")
        if not cam["ok"]:
            warn.append("摄像头不可用")

    if bad:
        return {"level": "bad", "line": bad[0], "why": bad[1:] + warn}
    if warn:
        return {"level": "warn", "line": warn[0], "why": warn[1:]}
    return {"level": "ok",
            "line": f"整套都在跑 · {_ago(gap)}还听到有人说话", "why": []}


def _collect() -> Dict[str, Any]:
    """Everything the page needs, gathered fresh."""
    # Something on this machine drops connections to dead loopback ports instead
    # of refusing them, so an HTTP call to a daemon that is not running costs the
    # full timeout. The listener table is already in hand, so ask it first — and
    # "port not listening" and "port listening but silent" are different faults.
    serving = _listening(DAEMON_PORT)
    status = _get(f"{DAEMON}/api/daemon/status") if serving else None
    media = specs = running = None
    if status is not None:
        media = _get(f"{DAEMON}/api/media/status")
        specs = _get(f"{DAEMON}/api/camera/specs")
        running = _get(f"{DAEMON}/api/move/running")

    backend = (status or {}).get("backend_status") or {}
    loop = backend.get("control_loop_stats") or {}
    hz = loop.get("mean_control_loop_frequency")
    photos = _photos()
    available = bool((media or {}).get("available"))
    no_media = bool((media or {}).get("no_media"))

    data = {
        "now": datetime.now().strftime("%H:%M:%S"),
        # The page prints these rather than its own copy, so a label can never
        # name a different port from the one actually checked.
        "ports": {"daemon": DAEMON_PORT, "realtime": REALTIME_PORT, "app": APP_PORT},
        "robot": {
            "up": status is not None,
            "serving": serving,
            "state": (status or {}).get("state"),
            "error": (status or {}).get("error") or backend.get("error"),
            "version": (status or {}).get("version"),
            "desktop_client": bool((status or {}).get("desktop_app_daemon")),
            "motors": backend.get("motor_control_mode"),
            "hz": round(hz, 1) if isinstance(hz, (int, float)) else None,
            "errors": loop.get("nb_error"),
            "moving": None if running is None else bool(running),
        },
        "camera": {
            "known": media is not None,
            "ok": available and not no_media,
            "released": bool((media or {}).get("released")),
            "no_media": no_media,
            "model": (specs or {}).get("name"),
        },
        "voice": voice_state(),
        "glasses": {
            "photos": len(photos),
            "last_ago": _gap(photos[-1] if photos else None),
            "diary_up": _listening(DIARY_PORT),
            "diary_port": DIARY_PORT,
        },
    }
    data["verdict"] = verdict(data)
    return data


def snapshot() -> Dict[str, Any]:
    """The latest reading, recomputed at most once per SNAP_TTL."""
    stamp, cached = _CACHE["snap"]
    if cached is not None and time.time() - stamp < SNAP_TTL:
        return cached
    data = _collect()
    _CACHE["snap"] = (time.time(), data)
    return data


PAGE = """<!doctype html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Reachy · 运行状态</title>
<style>
 :root{--bg:#0f1115;--card:#171a21;--line:#262b36;--dim:#8b93a7;--ok:#3ddc97;
       --bad:#ff6b6b;--warn:#ffc857;--fg:#e8ecf4}
 *{box-sizing:border-box}
 body{margin:0;padding:16px;background:var(--bg);color:var(--fg);
      font:15px/1.5 -apple-system,"Segoe UI",system-ui,sans-serif}
 h1{font-size:17px;margin:0 0 4px;font-weight:600}
 .sub{color:var(--dim);font-size:13px;margin-bottom:14px}
 .verdict{border:1px solid;border-radius:14px;padding:14px 16px;margin-bottom:12px}
 .verdict .line{font-size:19px;font-weight:700;line-height:1.35}
 .verdict .why{color:var(--fg);opacity:.75;font-size:13px;margin-top:6px}
 .verdict .why div{margin-top:2px}
 .v-ok{border-color:rgba(61,220,151,.45);background:rgba(61,220,151,.10)}
 .v-ok .line{color:var(--ok)}
 .v-warn{border-color:rgba(255,200,87,.5);background:rgba(255,200,87,.10)}
 .v-warn .line{color:var(--warn)}
 .v-bad{border-color:var(--bad);background:rgba(255,107,107,.14);
        animation:breathe 2.2s ease-in-out infinite}
 .v-bad .line{color:var(--bad)}
 @keyframes breathe{50%{border-color:rgba(255,107,107,.35);
                        background:rgba(255,107,107,.05)}}
 .alarm{border:1px solid var(--bad);background:rgba(255,107,107,.16);
        border-radius:12px;padding:12px 14px;margin-bottom:12px;
        color:var(--bad);font-weight:700;font-size:15px}
 .fresh{display:grid;gap:12px;margin-bottom:12px;
        grid-template-columns:repeat(auto-fit,minmax(260px,1fr))}
 .tile{background:var(--card);border:1px solid var(--line);border-radius:12px;
       padding:12px 14px;min-width:0}
 .tile .lab{font-size:12px;color:var(--dim);letter-spacing:.06em;font-weight:600}
 .tile .num{font-size:40px;font-weight:700;line-height:1.1;margin:2px 0 4px;
            font-variant-numeric:tabular-nums}
 .tile .unit{font-size:15px;font-weight:600;margin-left:6px;opacity:.85}
 .tile .word{font-size:26px}
 .tile .txt{font-size:13px;color:var(--dim);overflow:hidden;
            display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}
 .t-ok .num{color:var(--ok)}
 .t-warn .num{color:var(--warn)}
 .t-warn{border-color:rgba(255,200,87,.45)}
 .t-bad .num{color:var(--bad)}
 .t-bad{border-color:var(--bad);background:rgba(255,107,107,.10);
        animation:breathe 2.2s ease-in-out infinite}
 .grid{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(300px,1fr))}
 .card{background:var(--card);border:1px solid var(--line);border-radius:12px;
       padding:14px;min-width:0}
 .card h2{font-size:13px;margin:0 0 10px;color:var(--dim);font-weight:600;
          letter-spacing:.06em;text-transform:uppercase}
 .row{display:flex;justify-content:space-between;gap:12px;padding:5px 0;
      border-bottom:1px solid var(--line)}
 .row:last-child{border:0}
 .k{color:var(--dim);white-space:nowrap}
 .v{text-align:right;font-variant-numeric:tabular-nums;min-width:0;
    overflow-wrap:anywhere}
 .none{color:var(--bad);opacity:.8}
 .dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:7px;
      vertical-align:1px}
 .ok{background:var(--ok)}.bad{background:var(--bad)}.warn{background:var(--warn)}
 .big{font-size:15px;font-weight:600}
 .quote{font-size:13.5px;margin:2px 0 0;line-height:1.45;overflow-wrap:anywhere}
 .who{color:var(--dim);font-size:12px}
 .turns{display:grid;gap:0 20px;grid-template-columns:repeat(auto-fit,minmax(330px,1fr))}
 .turn{padding:8px 0;border-bottom:1px solid var(--line);min-width:0}
 .empty{color:var(--dim);font-size:13.5px}
 body.stale #fresh,body.stale #grid,body.stale #alarm{opacity:.4}
 @media(min-width:640px){.wide{grid-column:1/-1}}
 @media(max-width:430px){
   body{padding:12px}
   .grid{grid-template-columns:1fr}
   .tile .num{font-size:34px}
   .verdict .line{font-size:17px}
 }
</style></head><body>
<h1>Reachy · 运行状态</h1>
<div class="sub" id="clock">读取中…</div>
<div class="verdict v-warn" id="verdict"><div class="line">读取中…</div></div>
<div id="alarm"></div>
<div class="fresh" id="fresh"></div>
<div class="grid" id="grid"></div>
<script>
const esc = s => String(s==null?'':s).replace(/[&<>]/g,
  c => ({'&':'&amp;','<':'&lt;','>':'&gt;'})[c]);
const dot = ok => `<span class="dot ${ok===null?'warn':ok?'ok':'bad'}"></span>`;
const row = (k,v) => `<div class="row"><span class="k">${k}</span><span class="v">${v}</span></div>`;
const card = (t,rows,cls='') => `<div class="card ${cls}"><h2>${t}</h2>${rows.join('')}</div>`;
// A missing reading must read as missing, never as an empty cell or a zero.
const gone = (t='无数据') => `<span class="none">${t}</span>`;

function ago(s){
  if (s===null || s===undefined) return {n:'从未', u:'', lvl:'warn', word:true};
  if (s < 60)   return {n:Math.round(s), u:'秒前', lvl:'ok'};
  if (s < 300)  return {n:Math.floor(s/60), u:'分钟前', lvl:'warn'};
  if (s < 3600) return {n:Math.floor(s/60), u:'分钟前', lvl:'bad'};
  return {n:(s/3600).toFixed(1), u:'小时前', lvl:'bad'};
}

function tile(lab, secs, text){
  const a = ago(secs);
  return `<div class="tile t-${a.lvl}"><div class="lab">${lab}</div>
    <div class="num${a.word ? ' word' : ''}">${a.n}<span class="unit">${a.u}</span></div>
    <div class="txt">${text ? esc(text) : '日志里没有记录'}</div></div>`;
}

let snap = null, at = 0, fails = 0;
const LOST = 10;   // seconds without a successful poll before the page says so

async function poll(){
  try {
    const r = await fetch('/api/status', {cache:'no-store'});
    snap = await r.json(); at = Date.now(); fails = 0;
  } catch(e){ fails++; }
  draw();
}

function draw(){
  const drift = (Date.now() - at) / 1000;   // keep the seconds climbing between polls
  const clock = document.getElementById('clock');
  const box = document.getElementById('verdict');
  // One dropped poll is a hiccup, not an outage; shouting about it would train
  // her to ignore the banner. Only a snapshot gone properly stale counts.
  const lost = !snap || drift > LOST;

  if (!snap){
    clock.textContent = '状态服务不可用';
    box.className = 'verdict v-bad';
    box.innerHTML = '<div class="line">状态页自己拿不到数据</div>'
      + '<div class="why">8770 端口上的 status_board.py 可能已经退出</div>';
    return;
  }
  document.body.classList.toggle('stale', lost);
  clock.textContent = '最后更新 ' + snap.now + ' · 每 3 秒自动刷新'
    + (fails ? ' · 连续 ' + fails + ' 次没取到' : '');

  const vd = snap.verdict;
  if (lost){
    box.className = 'verdict v-bad';
    box.innerHTML = `<div class="line">状态页已经 ${drift.toFixed(0)} 秒没拿到数据</div>`
      + '<div class="why">下面是旧快照，不代表现在的状态 · 检查 8770 端口上的 status_board.py</div>';
  } else {
    box.className = 'verdict v-' + vd.level;
    box.innerHTML = `<div class="line">${esc(vd.line)}</div>` +
      (vd.why.length ? `<div class="why">${vd.why.map(w=>`<div>· ${esc(w)}</div>`).join('')}</div>` : '');
  }

  const r = snap.robot, v = snap.voice, c = snap.camera, P = snap.ports;
  document.getElementById('alarm').innerHTML = r.desktop_client
    ? '<div class="alarm">先退出官方桌面客户端，机器人才会交回来 —— 在那之前语音、动作、摄像头都是死的</div>'
    : '';

  document.getElementById('fresh').innerHTML =
    tile('最后听到', v.heard_ago===null ? null : v.heard_ago + drift, v.heard_text) +
    tile('最后回复', v.reply_ago===null ? null : v.reply_ago + drift, v.reply_text);

  const robot = card('机器人', [
    row('连接', r.up ? dot(r.state==='running' && !r.error)
        + (r.state==='running' && !r.error ? '正常' : esc(r.error || r.state || '异常'))
      : dot(false) + (r.serving ? '端口在听但不回应' : '没在跑 · ' + P.daemon + ' 端口没人监听')),
    row('电机', r.up ? dot(r.motors==='enabled') + esc(r.motors || '未知') : gone()),
    row('控制环', r.hz===null ? gone() : r.hz + ' Hz'),
    row('控制环错误', r.errors===null||r.errors===undefined ? gone() : r.errors + ' 次'),
    row('正在动作', r.moving===null ? gone() : (r.moving ? '是' : '否')),
    row('daemon 版本', r.version ? esc(r.version) : gone()),
    row('官方客户端占用', r.up ? (r.desktop_client
        ? '<span class="none">是 · robot 被它独占</span>' : '否') : gone()),
  ]);

  const voice = card('语音链路', [
    row('服务端 :' + P.realtime, dot(v.up) + (v.up ? '在线' : '<span class="none">离线</span>')),
    row('对话应用 :' + P.app, dot(v.app_up) + (v.app_up ? '在线' : '<span class="none">离线</span>')),
    row('转写模型', v.stt ? esc(v.stt) : gone('日志里没有')),
    row('日志内轮次', v.turns_seen + ' 轮'),
    row('近几轮中位耗时', v.median===null ? gone('暂无') : v.median + ' 秒'),
  ]);

  // Two different eyes, and confusing them cost us an evening: the media
  // device is Reachy's own camera, the photo count comes from the glasses.
  const cam = card('Reachy 的摄像头', [
    row('媒体设备', !c.known ? gone() : dot(c.ok) + (c.ok ? '可用'
      : (c.no_media ? '未启用 no_media' : '被占用或已释放'))),
    row('机型', c.model ? esc(c.model) : gone()),
    row('看到了什么', '见下方"最近几轮"里它自己描述的画面'),
  ]);

  const glasses = card('眼镜', [
    row('今日照片', snap.glasses.photos + ' 张'),
    row('最近一张', snap.glasses.last_ago===null ? gone('从未')
      : (() => { const a = ago(snap.glasses.last_ago + drift); return a.n + ' ' + a.u; })()),
    row('日记页', (snap.glasses.diary_up ? dot(true) : dot(false))
      + '<a href="http://127.0.0.1:' + snap.glasses.diary_port + '/" target="_blank">127.0.0.1:'
      + snap.glasses.diary_port + '</a>'),
  ]);

  let turns = '<div class="card wide"><h2>最近几轮</h2>';
  if (!v.turns.length) turns += '<div class="empty">日志里还没有一轮完整对话</div>';
  turns += '<div class="turns">';
  for (const t of v.turns.slice().reverse()){
    const total = (t.model||0) + (t.speech||0);
    turns += `<div class="turn">
      <div class="row" style="border:0;padding:0 0 4px">
        <span class="big">${total ? total.toFixed(1)+' 秒' : gone('耗时缺失')}</span>
        <span class="who">模型 ${t.model===null?'—':t.model+'s'} · 合成 ${t.speech===null?'—':t.speech+'s'}</span>
      </div>
      <div class="who">你说</div>
      <div class="quote">${t.heard ? esc(t.heard) : '<span class="empty">这轮日志里没有对应的 heard</span>'}</div>
      <div class="who" style="margin-top:4px">它说</div><div class="quote">${esc(t.reply)}</div>
    </div>`;
  }
  turns += '</div></div>';

  document.getElementById('grid').innerHTML = robot + voice + cam + glasses + turns;
}

poll();
setInterval(poll, 3000);
setInterval(draw, 500);   // the freshness numbers tick even while a poll is in flight
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    """Serves one page and one JSON endpoint."""

    def do_GET(self) -> None:  # noqa: N802 - name fixed by BaseHTTPRequestHandler
        """Answer the page or the status payload."""
        if self.path.startswith("/api/status"):
            body = json.dumps(snapshot(), ensure_ascii=False).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
        else:
            body = PAGE.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_: Any) -> None:
        """Stay quiet; the page polls several times a minute."""


def main(argv: Sequence[str] | None = None) -> int:
    """Serve the status page until interrupted."""
    parser = argparse.ArgumentParser(description="Local status board")
    parser.add_argument("--port", type=int, default=8770)
    args = parser.parse_args(argv)
    # Threaded: one slow daemon call must not queue up behind another tab's poll.
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"status board on http://127.0.0.1:{args.port}", flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        pass
