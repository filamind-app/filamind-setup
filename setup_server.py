# ======================================================================= #
#  FilaMind Setup - browser-finish server (the graphical finish, §14.5).   #
#  A minimal, dependency-free web wizard over the SAME engine the CLI uses: #
#  Python's stdlib http.server only. Gated by a session-scoped token that   #
#  is printed only in the terminal, so only the operator who launched it    #
#  can drive the install (LAN safety). GPL-3.0-or-later - FilaMind's own.    #
# ======================================================================= #
from __future__ import annotations

import json
import secrets
import socket
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from engine import SetupEngine, SetupError

# Raw string: the embedded JS keeps its own backslash escapes (\n, …) verbatim.
WIZARD_HTML = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>FilaMind Setup</title>
<style>
  :root{--bg:#0e0f12;--surface:#17171c;--surface2:#20202a;--border:#3a3320;--text:#f3ecd8;--muted:#9a917c;--gold:#d4af37;--teal:#2ba199;--red:#9e2b25}
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--text);font:16px/1.5 ui-sans-serif,system-ui,sans-serif}
  .wrap{max-width:760px;margin:0 auto;padding:28px 20px}
  h1{font-size:24px;margin:0 0 4px;display:flex;align-items:center;gap:10px}
  h1 .dot{width:30px;height:30px;border-radius:8px;background:var(--gold);color:var(--bg);display:flex;align-items:center;justify-content:center;font-weight:700}
  .sub{color:var(--muted);margin:0 0 22px}
  .card{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:16px 18px;margin:14px 0}
  .card h2{font-size:15px;margin:0 0 10px;color:var(--gold)}
  .row{display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid #2a2a30}
  .row:last-child{border-bottom:0}
  .ok{color:var(--teal)} .no{color:var(--muted)} .warn{color:var(--gold)}
  button{font:inherit;font-weight:600;border-radius:12px;padding:12px 18px;margin:6px 8px 6px 0;cursor:pointer;background:var(--surface2);color:var(--text);border:1px solid var(--border)}
  button.primary{background:var(--gold);color:var(--bg);border-color:transparent}
  button:disabled{opacity:.45;cursor:not-allowed}
  pre{background:#000;color:#cfe;border-radius:12px;padding:12px;max-height:260px;overflow:auto;white-space:pre-wrap;font:13px/1.5 ui-monospace,monospace}
  .empty{color:var(--muted)}
</style></head><body><div class="wrap">
  <h1><span class="dot">F</span>FilaMind Setup</h1>
  <p class="sub">Finish setting up the FilaMind suite from your browser.</p>
  <div class="card"><h2>This printer</h2><div id="probe"><span class="empty">Detecting&hellip;</span></div></div>
  <div class="card"><h2>What to do</h2><div id="actions"><span class="empty">&hellip;</span></div></div>
  <div class="card"><h2>Progress</h2><pre id="log">(idle)</pre></div>
<script>
  var t = new URLSearchParams(location.search).get('t') || '';
  var $ = function(id){ return document.getElementById(id); };
  function logln(s){ var p=$('log'); if(p.textContent==='(idle)') p.textContent=''; p.textContent+=s+'\n'; p.scrollTop=p.scrollHeight; }
  function esc(s){ return String(s).replace(/[&<>]/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;'}[c]; }); }
  function row(k,v,cls){ return '<div class="row"><span>'+esc(k)+'</span><span class="'+(cls||'')+'">'+esc(v)+'</span></div>'; }
  function render(d){
    var inst = Object.keys(d.installed||{}).filter(function(k){ return d.installed[k]; });
    $('probe').innerHTML =
      row('Operating system', d.os||'?') +
      row('Klipper', d.has_klipper?'detected':'not found', d.has_klipper?'ok':'no') +
      row('Moonraker', d.has_moonraker?'detected':'not found', d.has_moonraker?'ok':'no') +
      row('Components installed', inst.length? inst.join(', '):'none', inst.length?'ok':'no');
    var a = $('actions');
    var bare = (!d.has_klipper || !d.has_moonraker);
    var existing = ['mainsail','fluidd','klipperscreen'].filter(function(u){ return d.installed[u]; });
    if(bare){
      var missing = []; if(!d.has_klipper) missing.push('Klipper'); if(!d.has_moonraker) missing.push('Moonraker');
      a.innerHTML = '<p>This looks like a <b>fresh host</b>. FilaMind Setup installs the whole stack from scratch in one go - ' +
        esc(missing.join(' + '))+' + the FilaMind suite (flow + 3d).</p>' +
        '<button class="primary" onclick="run(\'install_suite\')">Install the full stack</button>';
    } else if(existing.length){
      a.innerHTML = '<p>Found an existing UI ('+esc(existing.join(', '))+'). FilaMind installs <b>alongside</b> it - nothing is removed.</p>' +
        '<button class="primary" onclick="run(\'install_suite\')">Install FilaMind alongside</button>' +
        '<button onclick="run(\'migrate\')">Migrate to FilaMind</button>';
    } else {
      a.innerHTML = '<button class="primary" onclick="run(\'install_suite\')">Install the FilaMind suite</button>';
    }
  }
  function setBusy(b){ var bs=document.querySelectorAll('#actions button'); for(var i=0;i<bs.length;i++) bs[i].disabled=b; }
  function probe(){
    fetch('/api/probe?t='+encodeURIComponent(t)).then(function(r){ return r.json(); }).then(function(d){
      if(d.error){ $('probe').innerHTML = '<span class="warn">'+esc(d.error)+'</span>'; return; }
      render(d);
    }).catch(function(e){ $('probe').innerHTML = '<span class="warn">'+esc(e)+'</span>'; });
  }
  function run(action){
    setBusy(true); logln('Starting: '+action+' …');
    fetch('/api/run?t='+encodeURIComponent(t), {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({action:action})})
      .then(function(r){ return r.json(); }).then(function(d){
        (d.log||[]).forEach(logln);
        logln(d.ok ? '✓ Done. You can close this tab.' : ('✗ Error: '+(d.error||'unknown')));
        setBusy(false); probe();
      }).catch(function(e){ logln('✗ '+e); setBusy(false); });
  }
  probe();
</script></div></body></html>
"""


def _lan_ip() -> str:
    """Best-effort LAN IP for the printed link; falls back to localhost."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


def _make_handler(token: str) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def _tok_ok(self) -> bool:
            got = parse_qs(urlparse(self.path).query).get("t", [""])[0]
            return bool(got) and secrets.compare_digest(got, token)

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, obj: object) -> None:
            self._send(code, json.dumps(obj).encode("utf-8"), "application/json")

        def do_GET(self) -> None:  # noqa: N802
            if not self._tok_ok():
                self._json(403, {"error": "missing or invalid one-time token"})
                return
            path = urlparse(self.path).path
            if path == "/":
                self._send(200, WIZARD_HTML.encode("utf-8"), "text/html; charset=utf-8")
            elif path == "/api/probe":
                try:
                    self._json(200, SetupEngine().probe())
                except SetupError as e:
                    self._json(500, {"error": str(e)})
            else:
                self._json(404, {"error": "not found"})

        def do_POST(self) -> None:  # noqa: N802
            if not self._tok_ok():
                self._json(403, {"error": "missing or invalid one-time token"})
                return
            if urlparse(self.path).path != "/api/run":
                self._json(404, {"error": "not found"})
                return
            length = int(self.headers.get("Content-Length") or 0)
            try:
                req = json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                self._json(400, {"error": "bad request body"})
                return
            action = req.get("action")
            logs: list[str] = []
            eng = SetupEngine(log=logs.append)
            try:
                if action == "install_suite":
                    eng.bootstrap(ask=lambda q, o: "install FilaMind alongside")
                elif action == "migrate":
                    eng.migrate()
                elif action == "install" and isinstance(req.get("id"), str):
                    eng.install(req["id"])
                else:
                    self._json(400, {"error": f"unknown action {action!r}"})
                    return
                self._json(200, {"ok": True, "log": logs})
            except SetupError as e:
                self._json(500, {"ok": False, "error": str(e), "log": logs})

        def log_message(self, *_a: object) -> None:  # quiet; the wizard shows its own progress
            return

    return Handler


def serve(port: int = 8077) -> None:
    """Start the browser-finish wizard and print the link (the token appears only here, in the
    terminal, so only the operator who launched it can drive setup over the LAN)."""
    token = secrets.token_urlsafe(18)
    httpd = ThreadingHTTPServer(("0.0.0.0", port), _make_handler(token))
    url = f"http://{_lan_ip()}:{port}/?t={token}"
    print("\nFinish in your browser - open this link (only this one works; the token is")
    print("printed only here, so nobody else on the network can drive the install):\n")
    print(f"  {url}\n")
    print("Leave this running while you use the wizard; press Ctrl-C when you are done")
    print("(or finish in the terminal instead with:  filamind-setup menu).\n")
    sys.stdout.flush()  # show the link immediately - serve_forever() then blocks
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped the setup server.")
        httpd.shutdown()
