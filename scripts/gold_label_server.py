"""Local browser pager for gold labeling.

Serves the 193 gold instances one screen at a time; every click writes the
label straight into runs/judge/gold/<item>.answers.psv (atomic rewrite),
so progress is durable and resumable — close the tab whenever.

Run:  .venv/bin/python scripts/gold_label_server.py   (then open the URL)
"""

from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from tellbench.judge.extract import JUDGE_DIR
from tellbench.judge.items import ITEMS

GOLD_DIR = JUDGE_DIR / "gold"
HOST, PORT = "127.0.0.1", 8787


def read_answers(item_id: str) -> list[tuple[str, str]]:
    """[(instance_key, label)] in file order; key may contain '|' — the
    label is after the LAST pipe (same contract as run_judge.py)."""
    path = GOLD_DIR / f"{item_id}.answers.psv"
    rows = []
    for line in path.read_text().splitlines():
        if line.strip():
            key, _, label = line.rpartition("|")
            rows.append((key, label.strip()))
    return rows


def write_label(item_id: str, key: str, label: str) -> None:
    path = GOLD_DIR / f"{item_id}.answers.psv"
    rows = read_answers(item_id)
    if key not in {k for k, _ in rows}:
        raise KeyError(f"unknown instance_key for {item_id}: {key}")
    updated = [(k, label if k == key else old) for k, old in rows]
    tmp = path.with_suffix(".psv.tmp")
    tmp.write_text("".join(f"{k}|{v}\n" for k, v in updated))
    tmp.replace(path)


def targeted_keys() -> set[tuple[str, str]] | None:
    """Optional focus list: runs/judge/gold/targeted.keys, one
    'item_id<TAB>instance_key' per line. Delete the file to serve all
    193 gold instances again."""
    path = GOLD_DIR / "targeted.keys"
    if not path.is_file():
        return None
    return {
        (line.split("\t", 1)[0], line.split("\t", 1)[1])
        for line in path.read_text().splitlines()
        if "\t" in line
    }


def load_data() -> list[dict]:
    focus = targeted_keys()
    data = []
    for item_id, spec in ITEMS.items():
        answers = read_answers(item_id)
        if focus is not None:
            answers = [(k, lbl) for k, lbl in answers if (item_id, k) in focus]
        if not answers:
            continue
        wanted = {k for k, _ in answers}
        payloads: dict[str, dict] = {}
        inst_path = JUDGE_DIR / f"instances_{item_id}.jsonl"
        for line in inst_path.read_text().splitlines():
            inst = json.loads(line)
            if inst["instance_key"] in wanted:
                payloads[inst["instance_key"]] = inst["payload"]
        missing = wanted - set(payloads)
        if missing:
            raise RuntimeError(f"{item_id}: {len(missing)} gold keys missing "
                               f"from {inst_path.name}: {sorted(missing)[:2]}")
        data.append({
            "item_id": item_id,
            "question": spec.question,
            "tokens": list(spec.verdict_tokens),
            "instances": [
                {"key": k, "label": lbl, "payload": payloads[k]}
                for k, lbl in answers
            ],
        })
    return data


PAGE = """<!doctype html><html><head><meta charset="utf-8">
<title>tellbench gold labeling</title><style>
body{margin:0;font:14px/1.45 -apple-system,sans-serif;background:#111;color:#ddd;display:flex;height:100vh}
#side{width:230px;background:#181818;padding:12px;overflow-y:auto;flex-shrink:0}
#side h3{margin:4px 0 10px;font-size:13px;color:#999}
.it{padding:6px 8px;border-radius:6px;cursor:pointer;margin-bottom:2px;font-size:12px}
.it:hover{background:#242424}.it.cur{background:#2c3a55}
.it .n{color:#8a8}.it .n.done{color:#4c4;font-weight:600}
#main{flex:1;display:flex;flex-direction:column;overflow:hidden}
#head{padding:10px 18px;background:#1c1c1c;border-bottom:1px solid #333}
#q{font-size:15px;font-weight:600;color:#fff}#pos{color:#888;font-size:12px;margin-top:3px}
#pay{flex:1;overflow-y:auto;padding:14px 18px}
#pay h4{margin:14px 0 4px;color:#7ab;font-size:12px;text-transform:uppercase}
#pay pre{background:#1a1a1a;border:1px solid #2a2a2a;border-radius:8px;padding:10px;
white-space:pre-wrap;word-break:break-word;margin:0;font-size:12.5px;max-height:45vh;overflow-y:auto}
#bar{padding:12px 18px;background:#1c1c1c;border-top:1px solid #333;display:flex;gap:10px;align-items:center}
button{font:600 14px -apple-system,sans-serif;padding:10px 22px;border-radius:8px;border:1px solid #444;
background:#262626;color:#eee;cursor:pointer}
button:hover{background:#333}button.sel{background:#2b6a3f;border-color:#3c8}
button.nav{padding:10px 14px;font-weight:400;color:#aaa}
#hint{margin-left:auto;color:#666;font-size:12px}
#done{color:#4c4;font-weight:600;font-size:13px;padding:0 8px}
</style></head><body>
<div id="side"><h3>gold labeling</h3><div id="items"></div></div>
<div id="main"><div id="head"><div id="q"></div><div id="pos"></div></div>
<div id="pay"></div><div id="bar"></div></div>
<script>
let DATA=[],ii=0,ci=0;
const flat=()=>DATA[ii].instances[ci];
async function boot(){DATA=await(await fetch('/api/data')).json();
 const first=firstUnlabeled();ii=first[0];ci=first[1];render();}
function firstUnlabeled(){for(let a=0;a<DATA.length;a++){const j=DATA[a].instances.findIndex(x=>!x.label);
 if(j>=0)return[a,j];}return[0,0];}
function totals(){let d=0,t=0;DATA.forEach(x=>x.instances.forEach(y=>{t++;if(y.label)d++;}));return[d,t];}
function render(){
 const side=document.getElementById('items');side.innerHTML='';
 DATA.forEach((x,a)=>{const done=x.instances.filter(y=>y.label).length;
  const el=document.createElement('div');el.className='it'+(a===ii?' cur':'');
  el.innerHTML=`${x.item_id}<br><span class="n${done===x.instances.length?' done':''}">${done}/${x.instances.length}</span>`;
  el.onclick=()=>{ii=a;ci=0;render();};side.appendChild(el);});
 const it=DATA[ii],inst=flat(),[d,t]=totals();
 document.getElementById('q').textContent=it.question;
 document.getElementById('pos').textContent=
  `${it.item_id} — instance ${ci+1}/${it.instances.length} — overall ${d}/${t} labeled`;
 const pay=document.getElementById('pay');pay.innerHTML='';
 Object.entries(inst.payload).forEach(([k,v])=>{const h=document.createElement('h4');h.textContent=k;
  const p=document.createElement('pre');p.textContent=v;pay.appendChild(h);pay.appendChild(p);});
 pay.scrollTop=0;
 const bar=document.getElementById('bar');bar.innerHTML='';
 const back=document.createElement('button');back.className='nav';back.textContent='\\u2190 prev';
 back.onclick=()=>nav(-1);bar.appendChild(back);
 it.tokens.forEach((tok,n)=>{const b=document.createElement('button');
  b.textContent=`${n+1}: ${tok}`;if(inst.label===tok)b.className='sel';
  b.onclick=()=>label(tok);bar.appendChild(b);});
 const clr=document.createElement('button');clr.className='nav';clr.textContent='clear';
 clr.onclick=()=>label('');bar.appendChild(clr);
 const fwd=document.createElement('button');fwd.className='nav';fwd.textContent='next \\u2192';
 fwd.onclick=()=>nav(1);bar.appendChild(fwd);
 if(d===t){const s=document.createElement('span');s.id='done';s.textContent=`ALL ${t} DONE`;bar.appendChild(s);}
 const hint=document.createElement('span');hint.id='hint';
 hint.textContent='keys: 1/2 label \\u00b7 \\u2190/\\u2192 move \\u00b7 0 clear';bar.appendChild(hint);}
async function label(tok){const inst=flat();
 const r=await fetch('/api/label',{method:'POST',headers:{'Content-Type':'application/json'},
  body:JSON.stringify({item_id:DATA[ii].item_id,key:inst.key,label:tok})});
 if(!r.ok){alert('save failed: '+await r.text());return;}
 inst.label=tok;if(tok)nav(1);else render();}
function nav(dir){const n=ci+dir;
 if(n>=DATA[ii].instances.length){if(ii<DATA.length-1){ii++;ci=0;}else{ci=DATA[ii].instances.length-1;}}
 else if(n<0){if(ii>0){ii--;ci=DATA[ii].instances.length-1;}else{ci=0;}}
 else{ci=n;}render();}
document.addEventListener('keydown',e=>{
 if(e.key==='ArrowRight')nav(1);else if(e.key==='ArrowLeft')nav(-1);
 else if(e.key==='1')label(DATA[ii].tokens[0]);else if(e.key==='2')label(DATA[ii].tokens[1]);
 else if(e.key==='0')label('');});
boot();
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # quiet
        pass

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/":
            self._send(200, PAGE.encode(), "text/html; charset=utf-8")
        elif self.path == "/api/data":
            try:
                body = json.dumps(load_data()).encode()
                self._send(200, body, "application/json")
            except Exception as exc:  # noqa: BLE001 — surfaced to the page
                self._send(500, str(exc).encode(), "text/plain")
        else:
            self._send(404, b"not found", "text/plain")

    def do_POST(self):
        if self.path != "/api/label":
            self._send(404, b"not found", "text/plain")
            return
        try:
            n = int(self.headers.get("Content-Length", "0"))
            req = json.loads(self.rfile.read(n))
            item_id, key, label = req["item_id"], req["key"], req["label"]
            tokens = ITEMS[item_id].verdict_tokens
            if label not in ("", *tokens):
                raise ValueError(f"label {label!r} not in {tokens} or empty")
            write_label(item_id, key, label)
            self._send(200, b"ok", "text/plain")
        except Exception as exc:  # noqa: BLE001 — surfaced to the page
            self._send(400, str(exc).encode(), "text/plain")


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"gold labeling pager: http://{HOST}:{PORT}/  (Ctrl-C to stop)")
    server.serve_forever()


if __name__ == "__main__":
    main()
