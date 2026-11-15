"""生成两个静态页面（双击即可打开，无需服务器）：
- labels/labeling_sheet.html：盲标页面，不显示模型/组别/评审分；本地暂存，导出 CSV 覆盖 labels/human_labels.csv
- viewer/index.html：216 关浏览器（3 组 × 24 spec × 3 次采样），带规则检查、v3 集成分数、各评审答出的问题+原文证据、
  合格判定，以及「定向重写」前后对比
同时导出 labels/labeling_sheet_full.csv（含关卡全文，适合用 Excel/飞书表格标注）。"""
import json, glob, csv, pathlib, html
ROOT = pathlib.Path(__file__).resolve().parent.parent
DIMS = ["逻辑自洽性", "趣味性", "难度匹配度", "可玩性"]
recs = {json.load(open(f))["level_id"]: json.load(open(f)) for f in sorted(glob.glob(str(ROOT / "data/levels/*.json")))}
L = lambda p: {json.loads(l)["level_id"]: json.loads(l) for l in open(ROOT / p)}
import sys; sys.path.insert(0, str(ROOT))
from levelgen.checks import run_checks
from levelgen.systems import all_systems
from levelgen.rewrite import PROBLEM
J1, V3 = L("eval/judge_results.jsonl"), L("eval/judge_v3_results.jsonl")
RW = {json.loads(l)["base_level_id"]: json.loads(l) for l in open(ROOT / "eval/rewrite_results.jsonl")} if (ROOT / "eval/rewrite_results.jsonl").exists() else {}
rws = {json.load(open(f))["base_level_id"]: json.load(open(f)) for f in glob.glob(str(ROOT / "data/rewrites/*.json"))}
SYS, _, _ = all_systems(); ENS = SYS["v3 三家族集成 -cal"]
mp = json.load(open(ROOT / "labels/label_set_mapping.json"))
rubric = (ROOT / "prompts/rubric.md").read_text()

def lv_text(r):
    lv = r["level"] or {}
    return {"title": lv.get("title", ""), "scene": lv.get("scene", ""), "goal": lv.get("goal", ""),
            "choices": [{"id": c.get("id"), "text": c.get("text"), "outcome": c.get("outcome"), "result": c.get("result"), "next": c.get("next")}
                        for c in (lv.get("choices") or []) if isinstance(c, dict)], "raw": r["raw"] if r["level"] is None else ""}

# ---------- 标注页 ----------
items = []
for m in mp:
    r = recs[m["level_id"]]; s = r["spec"]
    items.append({"label_id": m["label_id"], "theme": s["theme"], "difficulty": s["difficulty"], "difficulty_def": s["difficulty_def"],
                  "persona": s["persona"], "persona_desc": s["persona_desc"], **lv_text(r)})
with open(ROOT / "labels/labeling_sheet_full.csv", "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f); w.writerow(["label_id", "主题", "难度", "画像", "标题", "场景", "目标", "选项A", "选项B", "选项C", *DIMS, "标注人", "备注"])
    for it in items:
        ch = [f"{c['text']} → [{c['result']}/{c['next']}] {c['outcome']}" for c in it["choices"]] + [""] * 3
        w.writerow([it["label_id"], it["theme"], it["difficulty"], it["persona"], it["title"], it["scene"], it["goal"], *ch[:3], "", "", "", "", "", ""])
LABEL_HTML = """<!doctype html><html lang=zh><meta charset=utf-8><title>关卡人工标注</title>
<style>body{font-family:-apple-system,"PingFang SC",sans-serif;max-width:920px;margin:24px auto;padding:0 16px;color:#222;line-height:1.6}
.card{border:1px solid #ddd;border-radius:10px;padding:16px;margin:16px 0}.meta{color:#666;font-size:13px}.ch{background:#f7f7f9;border-radius:6px;padding:8px;margin:6px 0}
.tag{display:inline-block;font-size:12px;background:#eef;padding:0 6px;border-radius:4px;margin-left:6px}select{font-size:15px;margin-right:12px}
.bar{position:sticky;top:0;background:#fff;padding:10px 0;border-bottom:1px solid #eee;z-index:2}button{font-size:15px;padding:6px 14px}
details{background:#fffbe6;padding:8px 12px;border-radius:8px}pre{white-space:pre-wrap;font-size:13px}.done{border-color:#4caf50}</style>
<h1>文字冒险关卡 · 人工标注</h1>
<p>共 __N__ 关，组别/模型已隐藏、顺序已打乱。请按评分标准逐关打 1–5 分。进度自动保存在本浏览器；全部完成后点「导出 CSV」，把下载的文件覆盖到 <code>labels/human_labels.csv</code>，再运行 <code>python scripts/compute_agreement.py</code>。</p>
<details><summary><b>评分标准（点开）</b></summary><pre>__RUBRIC__</pre></details>
<div class=bar>标注人：<input id=who placeholder="你的名字" > <span id=prog></span> <button onclick=exportCsv()>导出 CSV</button></div>
<div id=list></div>
<script>
const DIMS=__DIMS__, ITEMS=__ITEMS__, KEY='ieg_label_v1';
let st=JSON.parse(localStorage.getItem(KEY)||'{}');
const esc=s=>(s||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
function render(){document.getElementById('who').value=st.__who||'';
 document.getElementById('list').innerHTML=ITEMS.map(it=>{const v=st[it.label_id]||{};
 const sel=DIMS.map(d=>`${d} <select data-id="${it.label_id}" data-d="${d}"><option value="">-</option>${[1,2,3,4,5].map(k=>`<option ${v[d]==k?'selected':''}>${k}</option>`).join('')}</select>`).join('');
 const chs=it.choices.map(c=>`<div class=ch><b>${esc(c.id)}. ${esc(c.text)}</b><span class=tag>${esc(c.result)} / ${esc(c.next)}</span><br>${esc(c.outcome)}</div>`).join('')||`<pre>${esc(it.raw)}</pre>`;
 const done=DIMS.every(d=>v[d]);
 return `<div class="card ${done?'done':''}"><h3>${it.label_id} · ${esc(it.title)}</h3>
 <div class=meta>主题：${esc(it.theme)}｜难度：${it.difficulty}（${esc(it.difficulty_def)}）｜画像：${esc(it.persona)}（${esc(it.persona_desc)}）</div>
 <p>${esc(it.scene)}</p><p><b>目标：</b>${esc(it.goal)}</p>${chs}<p>${sel}</p>
 <input style="width:100%" placeholder="备注（为什么扣分）" data-id="${it.label_id}" data-d="备注" value="${esc(v['备注']||'')}"></div>`}).join('');
 const n=ITEMS.filter(it=>DIMS.every(d=>(st[it.label_id]||{})[d])).length;document.getElementById('prog').textContent=`已完成 ${n}/${ITEMS.length}`;}
document.addEventListener('change',e=>{const id=e.target.dataset.id,d=e.target.dataset.d;if(e.target.id=='who'){st.__who=e.target.value}else if(id){st[id]=st[id]||{};st[id][d]=e.target.value}
 localStorage.setItem(KEY,JSON.stringify(st));render();});
function exportCsv(){const q=s=>'"'+String(s||'').replace(/"/g,'""')+'"';
 const rows=[['label_id',...DIMS,'标注人','备注'].join(',')].concat(ITEMS.map(it=>{const v=st[it.label_id]||{};return [it.label_id,...DIMS.map(d=>v[d]||''),q(st.__who),q(v['备注'])].join(',')}));
 const a=document.createElement('a');a.href=URL.createObjectURL(new Blob(['\\ufeff'+rows.join('\\n')],{type:'text/csv'}));a.download='human_labels.csv';a.click();}
render();
</script></html>"""
(ROOT / "labels/labeling_sheet.html").write_text(LABEL_HTML.replace("__N__", str(len(items))).replace("__RUBRIC__", html.escape(rubric))
    .replace("__DIMS__", json.dumps(DIMS, ensure_ascii=False)).replace("__ITEMS__", json.dumps(items, ensure_ascii=False)), encoding="utf-8")

# ---------- 浏览器 ----------
def problems(v):
    out = []
    for j, a in (v.get("raw_answers") or {}).items():
        for q, txt in PROBLEM.items():
            if (a or {}).get(q) is True: out.append({"judge": j, "q": q, "txt": txt, "ev": str((a.get("evidence") or {}).get(q, ""))})
    return out
rows = []
for lid, r in recs.items():
    v = V3[lid]; chk = run_checks(r["level"], r["spec"]) if r["level"] else {"checks": {"H1_合法JSON": [False, "无法解析"]}, "hard_pass": False}
    sc = {d: round(x, 2) for d, x in ENS[lid].items()}
    row = {"id": lid, "arm": r["arm"], "model": r["model"].split("/")[-1], "prompt": r["prompt"], "spec": r["spec"], **lv_text(r),
           "checks": chk["checks"], "hard_pass": v["hard_pass"], "ens": sc, "per": v["per_judge"], "v1": J1.get(lid, {}).get("final"),
           "qual": v["hard_pass"] and min(sc.values()) >= 3, "probs": problems(v),
           "one": {j: (a or {}).get("one_line", "") for j, a in (v.get("raw_answers") or {}).items()},
           "tension": {j: (a or {}).get("spec_tension", "") for j, a in (v.get("raw_answers") or {}).items()}}
    if lid in RW and lid in rws:
        o = RW[lid]; row["rw"] = {"feedback": o["feedback"], "after": o["after"], "qual": o["qualified_after"], **lv_text(rws[lid]),
                                  "pw": (o.get("pairwise") or {}).get("winner")}
    rows.append(row)
VIEW = """<!doctype html><html lang=zh><meta charset=utf-8><title>关卡 × 评测浏览器</title>
<style>body{font-family:-apple-system,"PingFang SC","Noto Sans CJK SC",sans-serif;margin:0;color:#222}#side{position:fixed;left:0;top:0;bottom:0;width:340px;overflow:auto;border-right:1px solid #ddd;padding:10px;box-sizing:border-box;background:#fafafa}
#main{margin-left:350px;padding:16px 24px;max-width:960px;line-height:1.6}.it{padding:5px 6px;border-radius:6px;cursor:pointer;font-size:13px}.it:hover,.it.on{background:#e3e8ff}
.b{display:inline-block;min-width:26px;text-align:center;border-radius:4px;color:#fff;font-size:12px;margin-left:4px}.ch{background:#f4f5f8;border-radius:6px;padding:8px;margin:6px 0}
table{border-collapse:collapse}td,th{border:1px solid #ddd;padding:3px 8px;font-size:13px}.bad{color:#c62828}.ok{color:#2e7d32}.tag{display:inline-block;font-size:12px;background:#e8f5e9;padding:0 6px;border-radius:4px;margin:2px}
.rw{border-left:4px solid #5c6bc0;padding-left:12px;margin-top:20px}.q{font-weight:bold}.stat{font-size:12px;color:#555;margin:6px 0}</style>
<div id=side><b>关卡 × 评测浏览器</b><div class=stat id=stat></div>组 <select id=fa><option value="">全部</option><option>A</option><option>B</option><option>C</option></select>
难度 <select id=fd><option value="">全部</option><option>简单</option><option>普通</option><option>困难</option><option value=adv>对抗</option></select>
<select id=fq><option value="">全部</option><option value=1>合格</option><option value=0>不合格</option><option value=rw>有重写</option></select><br>
排序 <select id=fs><option value=id>编号</option><option value=lo>均分↑</option><option value=hi>均分↓</option></select><div id=items></div></div>
<div id=main></div>
<script>const R=__ROWS__,D=["逻辑自洽性","趣味性","难度匹配度","可玩性"];
const esc=s=>(s==null?'':String(s)).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
const avg=s=>D.reduce((a,d)=>a+(s[d]||0),0)/4, col=v=>v>=3.5?'#2e7d32':v>=3?'#f9a825':'#c62828';
function list(){const a=fa.value,d=fd.value,q=fq.value,s=fs.value;let xs=R.filter(r=>(!a||r.arm==a)&&(!d||(d=='adv'?r.spec.adversarial:(!r.spec.adversarial&&r.spec.difficulty==d)))&&(!q||(q=='rw'?r.rw:(r.qual==(q=='1')))));
 if(s!='id')xs.sort((x,y)=>(avg(x.ens)-avg(y.ens))*(s=='lo'?1:-1));
 stat.textContent=`显示 ${xs.length} 关，合格 ${xs.filter(r=>r.qual).length}`;
 items.innerHTML=xs.map(r=>`<div class=it onclick="show('${r.id}')" id="i_${r.id}">${r.qual?'✅':r.hard_pass?'⚠️':'⛔'} ${r.id}${r.rw?(r.rw.qual?' ↻✅':' ↻'):''}<span class=b style="background:${col(avg(r.ens))}">${avg(r.ens).toFixed(2)}</span></div>`).join('');}
const lvl=r=>`<p>${esc(r.scene)}</p><p><b>目标：</b>${esc(r.goal)}</p>${r.choices.map(c=>`<div class=ch><b>${esc(c.id)}. ${esc(c.text)}</b> <code>${esc(c.result)}/${esc(c.next)}</code><br>${esc(c.outcome)}</div>`).join('')}${r.raw?`<pre>${esc(r.raw)}</pre>`:''}`;
function show(id){const r=R.find(x=>x.id==id);document.querySelectorAll('.it').forEach(e=>e.classList.remove('on'));const el=document.getElementById('i_'+id);if(el)el.classList.add('on');
 const chk=Object.entries(r.checks).map(([k,v])=>`<tr><td>${k}</td><td class=${v[0]?'ok':'bad'}>${v[0]?'通过':'失败'}</td><td>${esc(v[1])}</td></tr>`).join('');
 const line=(n,s)=>s?`<tr><td>${n}</td>${D.map(d=>`<td>${typeof s[d]=='number'?+s[d].toFixed(2):'-'}</td>`).join('')}</tr>`:'';
 const sc=`<tr><th></th>${D.map(d=>`<th>${d}</th>`).join('')}</tr>${line('<b>v3 集成-cal</b>',r.ens)}${line('DeepSeek',r.per.ds)}${line('GLM(思考)',r.per.glm)}${line('Hunyuan',r.per.hy)}${line('v1（第一轮）',r.v1)}`;
 const pr=r.probs.map(p=>`<li><span class=q>[${p.judge}·${p.q}]</span> ${esc(p.txt)}${p.ev?`<br><small>证据：${esc(p.ev)}</small>`:''}</li>`).join('')||'<li>无</li>';
 let rw='';if(r.rw){rw=`<div class=rw><h3>↻ 定向重写（同一模型，1 次）→ ${r.rw.qual?'✅ 合格':'仍不合格'}</h3><b>交给模型的修改意见：</b><ol>${r.rw.feedback.map(f=>`<li>${esc(f)}</li>`).join('')}</ol>
 <table><tr><th></th>${D.map(d=>`<th>${d}</th>`).join('')}</tr>${line('重写前',r.ens)}${line('重写后',r.rw.after)}</table>${r.rw.pw?`<p>独立成对复核（DeepSeek，正反序）：总体 <b>${{a:'重写后更好',b:'重写前更好',tie:'打平/顺序不一致'}[r.rw.pw.overall]}</b></p>`:''}<h4>${esc(r.rw.title)}</h4>${lvl(r.rw)}</div>`;}
 main.innerHTML=`<h2>${esc(r.title)||'(无法解析)'} <small>${r.id}</small> ${r.qual?'✅ 合格':'❌ 不合格'}</h2><p>组 ${r.arm}：${r.model} + ${r.prompt}｜主题：${esc(r.spec.theme)}｜难度：${r.spec.difficulty}｜画像：${r.spec.persona}${r.spec.adversarial?'｜<b>对抗样例</b>：'+esc(r.spec.why):''}</p>
 ${lvl(r)}<h3>评分（合格 = 规则层通过且 v3 集成-cal 四维都 ≥3）</h3><table>${sc}</table>
 <h3>评审答出的问题（附原文证据）</h3><ul>${pr}</ul><p class=stat>${Object.entries(r.one).map(([j,t])=>`${j}：${esc(t)}`).join('<br>')}</p>
 <h3>规则层</h3><table>${chk}</table>${rw}`;}
[fa,fd,fq,fs].forEach(e=>e.onchange=list);list();show(R.find(r=>r.rw&&r.rw.qual&&r.arm=='B')?.id||R[0].id);</script></html>"""
(ROOT / "viewer/index.html").write_text(VIEW.replace("__ROWS__", json.dumps(rows, ensure_ascii=False)), encoding="utf-8")
print("ok", len(items), len(rows))
