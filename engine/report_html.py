# -*- coding: utf-8 -*-
"""HTML-дашборд: автономный файл, открывается двойным кликом, без интернета."""
from __future__ import annotations
import os, json
import numpy as np
import pandas as pd
from reports import млн, цел, пц

СРЕЗЫ = [
 ("l1","L1_Группа планирования",["Группа планирования"]),
 ("l2","L2_Направление",["Товарное направление","Группа планирования"]),
 ("l3","L3_Группа 1",["Товарное направление","Группа 1"]),
 ("l4","L4_Группа 2",["Товарное направление","Группа 1","Группа 2"]),
 ("l5","L5_Группа 3",["Группа 1","Группа 2","Группа 3"]),
 ("br","B1_Бренд",["Бренд"]),
 ("bn","B2_Бренд x Направление",["Бренд","Товарное направление"]),
 ("w1","W1_Филиал",["Филиал"]),
 ("w2","W2_Тип склада",["Тип склада"]),
 ("w3","W3_Склад",["Склад"]),
 ("w4","W4_Направление x Склад",["Товарное направление","Склад"]),
 ("w5","W5_Группа1 x Склад",["Группа 1","Склад"]),
 ("w6","W6_Бренд x Склад",["Бренд","Склад"]),
 ("xyz","S1_Сегмент XYZ",["XYZ"]),
 ("abc","S4_ABC",["ABC"]),
 ("liq","S2_Ликвидность",["Признак ликвидности"]),
]


def _pack(df, keys):
    rows = []
    for _, r in df.iterrows():
        имя = " · ".join(str(r[k]) for k in keys if k in df.columns and pd.notna(r[k]))
        def f(v):
            return None if (v is None or pd.isna(v) or (isinstance(v, float) and not np.isfinite(v))) else float(v)
        м = f(r.get("Маржа_%"))
        rows.append({"n": имя, "sku": int(r.SKU), "dead": int(r["SKU_мёртвых"]),
                     "rev": float(r.Оборот), "mar": м if (м is None or abs(м) < 1e4) else None,
                     "st": float(r.Запас), "d": f(r.get("Дней_запаса")), "g": f(r.get("GMROI")),
                     "ep": float(r.Эконом_прибыль), "oos": f(r.get("OOS_%")), "z": f(r.get("Засол_%"))})
    return sorted(rows, key=lambda x: -x["rev"])


def _bars(labels, series, colors, height=170):
    n = len(labels) or 1; ns = len(series); W, H = 860, height
    pl, pb, pt = 54, 26, 12; iw = W - pl - 12; ih = H - pb - pt
    mx = max((max(s) if s else 0) for s in series) or 1
    gw = iw / n; bw = min(26, (gw - 8) / max(ns, 1))
    o = ['<svg viewBox="0 0 %d %d" class="chart">' % (W, H)]
    for t in range(5):
        y = pt + ih - ih*t/4
        o.append('<line class="grid" x1="%d" y1="%.1f" x2="%d" y2="%.1f"/>' % (pl, y, W-12, y))
        o.append('<text class="ax" x="%d" y="%.1f" text-anchor="end">%s</text>'
                 % (pl-6, y+3, ("%.0f" % (mx*t/4)).replace(".", ",")))
    for i, lab in enumerate(labels):
        x0 = pl + i*gw
        for j, s in enumerate(series):
            if i >= len(s): continue
            h = ih * (s[i]/mx)
            o.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="%s" rx="2"><title>%s · %s</title></rect>'
                     % (x0+(gw-bw*ns)/2+j*bw, pt+ih-h, bw-2, max(h, .5), colors[j], lab,
                        ("%.2f" % s[i]).replace(".", ",")))
        o.append('<text class="ax" x="%.1f" y="%d" text-anchor="middle">%s</text>' % (x0+gw/2, H-8, lab[:3]))
    return "".join(o) + "</svg>"


def dashboard(путь, св, списки, S, cfg, ряды, лог=print):
    порог = S["порог"]; хор = float(cfg["экономика"]["порог_gmroi_хороший"])
    лимит_sku = int(cfg["отчёты"]["sku_в_дашборде"])
    D = {}
    for ключ, имя, keys in СРЕЗЫ:
        if имя in св:
            D[ключ] = _pack(св[имя], keys)
    if "L6_SKU" in св:
        D["sku"] = _pack(св["L6_SKU"].head(лимит_sku), ["Название номенклатуры","Бренд"])

    мx = ""
    if "W4_Направление x Склад" in св:
        w4 = св["W4_Направление x Склад"]
        top = w4.groupby("Склад")["Оборот"].sum().sort_values(ascending=False).head(6).index.tolist()
        piv = w4.pivot_table(index="Товарное направление", columns="Склад", values="GMROI", aggfunc="sum")
        pst = w4.pivot_table(index="Товарное направление", columns="Склад", values="Запас", aggfunc="sum")
        порядок = w4.groupby("Товарное направление")["Оборот"].sum().sort_values(ascending=False).index
        кор = {c: c.replace(" РТГ","").replace("Основной склад","Осн.").replace("шоссе","")
                .replace("тракт","").replace(" LV","").replace("Cash&Carry","C&C").strip() for c in top}
        строки = []
        for d_ in порядок:
            if d_ not in piv.index: continue
            cells = []
            for c in top:
                v = piv.loc[d_, c] if c in piv.columns else np.nan
                s_ = pst.loc[d_, c] if c in pst.columns else np.nan
                if pd.isna(v) or pd.isna(s_) or s_ <= 10000:
                    cells.append('<td class="num mut">—</td>')
                else:
                    cls = "bad" if v < порог else ("good" if v >= хор else "")
                    cells.append('<td class="num %s">%s</td>' % (cls, пц(v, 2)))
            строки.append("<tr><td>%s</td>%s</tr>" % (str(d_)[:34], "".join(cells)))
        мx = ('<h2>Матрица GMROI: направление × склад</h2><div class="card"><table><thead><tr><th>Направление</th>'
              + "".join("<th>%s</th>" % кор[c][:18] for c in top) + "</tr></thead><tbody>"
              + "".join(строки) + '</tbody></table><div class="hint">Прочерк — запас менее 10 тыс. ₽.</div></div>')

    KPI = [
     ("Запас периметра", млн(S["запас"])+" млн ₽", "средний %s млн ₽" % млн(S["запас_средний"]), "blue"),
     ("Оборот за %d дней" % S["дней"], млн(S["оборот"])+" млн ₽", "валовая %s млн ₽" % млн(S["вп"]), "blue"),
     ("Маржа", пц(S["маржа"])+" %", "по обороту", "green"),
     ("GMROI", пц(S["gmroi"], 2), "порог владения %s" % пц(порог, 2), "green" if S["gmroi"] >= порог else "red"),
     ("Эконом. прибыль", млн(S["эконом_прибыль"])+" млн ₽/год", "валовая минус владение", "green" if S["эконом_прибыль"] > 0 else "red"),
     ("OOS", пц(S["oos"])+" %", "Fill Rate %s %%" % пц(S["fill_rate"]), "red"),
     ("Упущенные продажи", млн(S["упущено"])+" млн ₽", "DNS %s ед." % цел(S["dns"]), "red"),
     ("Не отрабатывают владение", "%d напр." % S["плохих_направлений"], "запас %s млн ₽" % млн(S["плохих_запас"]), "orange"),
    ]
    kpi = "".join('<div class="kpi %s"><div class="kl">%s</div><div class="kv">%s</div><div class="ks">%s</div></div>'
                  % (c, t, v, s) for t, v, s, c in KPI)

    мес = ряды.get("месяцы", [])
    ch1 = _bars(мес, [ряды.get("запас", []), ряды.get("оборот", [])], ["#2E5FA3", "#5BA85A"])
    ch2 = _bars(мес, [ряды.get("oos", [])], ["#C0504D"], 150)

    HTML = ШАБЛОН
    for k, v in {
        "__ДАТА__": S["дата"], "__SKU__": цел(S["sku"]), "__KPI__": kpi, "__ПОРОГ__": пц(порог, 2),
        "__CH1__": ch1, "__CH2__": ch2, "__MX__": мx, "__ДНЕЙ__": str(S["дней"]),
        "__ДАННЫЕ__": json.dumps(D, ensure_ascii=False),
        "__OWN__": str(порог), "__GOOD__": str(хор),
        "__ЛИМИТ__": str(int(cfg["отчёты"]["строк_в_дашборде"])),
    }.items():
        HTML = HTML.replace(k, v)
    open(путь, "w", encoding="utf-8").write(HTML)
    лог("   Дашборд: %.0f КБ, срезов %d" % (os.path.getsize(путь)/1024, len(D)))
    return путь


ШАБЛОН = """<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Категорийный дашборд РТГ</title>
<style>
:root{--bg:#f6f7f9;--card:#fff;--ink:#1a1d21;--mut:#6b7280;--line:#e3e6ea;--blue:#2E5FA3;--green:#2F7D32;--red:#C0392B;--orange:#D97706;--hi:#1F3864}
@media(prefers-color-scheme:dark){:root{--bg:#15181c;--card:#1d2126;--ink:#e8eaed;--mut:#9aa3ad;--line:#2c3238;--hi:#22304d}}
*{box-sizing:border-box}body{background:var(--bg);color:var(--ink);font:14px/1.5 -apple-system,Segoe UI,Roboto,Arial,sans-serif;margin:0;padding:20px}
.wrap{max-width:1280px;margin:0 auto}h1{font-size:23px;margin:0 0 3px}.sub{color:var(--mut);margin-bottom:18px;font-size:13px}
h2{font-size:16px;margin:26px 0 9px;padding-bottom:6px;border-bottom:2px solid var(--line)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px}
.kpi{background:var(--card);border:1px solid var(--line);border-left:3px solid var(--blue);border-radius:7px;padding:11px 13px}
.kpi.green{border-left-color:var(--green)}.kpi.red{border-left-color:var(--red)}.kpi.orange{border-left-color:var(--orange)}
.kl{font-size:10.5px;color:var(--mut);text-transform:uppercase;letter-spacing:.4px}
.kv{font-size:20px;font-weight:650;margin:3px 0 1px}.ks{font-size:11px;color:var(--mut)}
.card{background:var(--card);border:1px solid var(--line);border-radius:7px;padding:13px 15px;margin-top:10px;overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:12.5px}
th{background:var(--hi);color:#fff;text-align:left;padding:7px 9px;font-weight:600;font-size:11.5px;cursor:pointer;white-space:nowrap}
td{padding:5px 9px;border-bottom:1px solid var(--line)}td.num{text-align:right;font-variant-numeric:tabular-nums}
tr:hover td{background:rgba(46,95,163,.07)}td.bad{color:var(--red);font-weight:650}td.good{color:var(--green);font-weight:650}
td.mut{color:var(--mut)}.neg{color:var(--red);font-weight:600}
.tabs{display:flex;gap:5px;margin-top:11px;flex-wrap:wrap}
.tab{padding:6px 12px;border:1px solid var(--line);border-radius:6px;background:var(--card);cursor:pointer;font-size:12.5px;color:var(--ink)}
.tab[aria-selected="true"]{background:var(--hi);color:#fff;border-color:var(--hi)}
input.f{width:280px;max-width:100%;padding:6px 10px;border:1px solid var(--line);border-radius:6px;background:var(--card);color:var(--ink);font-size:12.5px;margin-bottom:9px}
.chart{width:100%;height:auto}line.grid{stroke:var(--line);stroke-width:1}text.ax{fill:var(--mut);font-size:10px}
.lg{display:flex;gap:16px;font-size:12px;color:var(--mut);margin:6px 0 2px}
.lg i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:5px}
.note{background:rgba(217,119,6,.09);border-left:3px solid var(--orange);padding:10px 13px;border-radius:5px;margin-top:10px;font-size:13px}
.hint{color:var(--mut);font-size:11.5px;margin-top:5px}
footer{color:var(--mut);font-size:11.5px;margin-top:24px;padding-top:12px;border-top:1px solid var(--line)}
</style></head><body><div class="wrap">
<h1>Категорийный дашборд · дивизион РТГ</h1>
<div class="sub">Данные на __ДАТА__ · период __ДНЕЙ__ дней · __SKU__ SKU</div>
<div class="grid">__KPI__</div>
<div class="note"><b>Как читать:</b> GMROI — валовая прибыль за год на рубль среднего запаса.
Порог __ПОРОГ__ — стоимость владения запасом. Ниже порога категория не окупает собственное хранение;
<span class="neg">красное — убыточно</span>, зелёное — заметно выше порога.</div>
<h2>Запас и оборот по месяцам, млн ₽</h2>
<div class="card"><div class="lg"><span><i style="background:#2E5FA3"></i>Запас</span><span><i style="background:#5BA85A"></i>Оборот</span></div>__CH1__</div>
<h2>Дефицит (OOS) по месяцам, %</h2><div class="card">__CH2__</div>
<h2>Товарная иерархия</h2>
<div class="tabs" id="tabsH">
<button class="tab" aria-selected="true" data-k="l1">Группы планирования</button>
<button class="tab" data-k="l2">Направления</button><button class="tab" data-k="l3">Группы 1</button>
<button class="tab" data-k="l4">Группы 2</button><button class="tab" data-k="l5">Группы 3</button>
<button class="tab" data-k="sku">SKU</button></div>
<div class="card"><input class="f" id="fH" placeholder="Фильтр по названию…"><div id="tH"></div>
<div class="hint">Клик по заголовку столбца — сортировка.</div></div>
<h2>Бренды</h2>
<div class="tabs" id="tabsB"><button class="tab" aria-selected="true" data-k="br">Бренды</button>
<button class="tab" data-k="bn">Бренд × направление</button><button class="tab" data-k="w6">Бренд × склад</button></div>
<div class="card"><input class="f" id="fB" placeholder="Фильтр по бренду…"><div id="tB"></div></div>
<h2>Склады</h2>
<div class="tabs" id="tabsW"><button class="tab" aria-selected="true" data-k="w1">Филиалы</button>
<button class="tab" data-k="w2">Типы складов</button><button class="tab" data-k="w3">Склады</button>
<button class="tab" data-k="w4">Направление × склад</button><button class="tab" data-k="w5">Группа 1 × склад</button></div>
<div class="card"><input class="f" id="fW" placeholder="Фильтр по складу или категории…"><div id="tW"></div></div>
__MX__
<h2>Сегменты</h2>
<div class="tabs" id="tabsS"><button class="tab" aria-selected="true" data-k="xyz">XYZ — стабильность спроса</button>
<button class="tab" data-k="abc">ABC по обороту</button><button class="tab" data-k="liq">Ликвидность</button></div>
<div class="card"><div id="tS"></div></div>
<footer>GMROI = валовая прибыль за год / средний запас по себестоимости. Отчёт сформирован автоматически.
Полные списки — в файле Excel рядом с этим дашбордом.</footer>
</div>
<script>
var D=__ДАННЫЕ__, OWN=__OWN__, GOOD=__GOOD__, LIM=__ЛИМИТ__;
var COLS=[{k:'n',t:'Наименование',f:'t'},{k:'sku',t:'SKU',f:'i'},{k:'dead',t:'Без продаж',f:'i'},
{k:'rev',t:'Оборот, млн ₽',f:'m'},{k:'mar',t:'Маржа',f:'p'},{k:'st',t:'Запас, млн ₽',f:'m'},
{k:'d',t:'Дней запаса',f:'d'},{k:'g',t:'GMROI',f:'g'},{k:'ep',t:'Эк. прибыль, млн ₽/год',f:'m'},
{k:'z',t:'Засолы',f:'p'},{k:'oos',t:'OOS',f:'p'}];
function nf(v,d){return v==null?'—':v.toLocaleString('ru-RU',{minimumFractionDigits:d,maximumFractionDigits:d});}
function cell(r,c){var v=r[c.k];
if(c.f=='t')return '<td>'+v+'</td>';
if(v==null)return '<td class="num mut">—</td>';
if(c.f=='i')return '<td class="num">'+nf(v,0)+'</td>';
if(c.f=='m')return '<td class="num'+(v<0?' neg':'')+'">'+nf(v/1e6,2)+'</td>';
if(c.f=='p')return '<td class="num">'+nf(v,1)+' %</td>';
if(c.f=='d')return '<td class="num">'+nf(v,0)+'</td>';
if(c.f=='g'){var cl=v<OWN?'bad':(v>=GOOD?'good':'');return '<td class="num '+cl+'">'+nf(v,2)+'</td>';}
return '<td class="num">'+v+'</td>';}
var ST={};
function render(box,key,filt,sortk,asc){
var rows=D[key]||[];
if(filt){var q=filt.toLowerCase();rows=rows.filter(function(r){return r.n.toLowerCase().indexOf(q)>-1;});}
if(sortk){rows=rows.slice().sort(function(a,b){var x=a[sortk],y=b[sortk];
if(x==null)return 1;if(y==null)return -1;
if(typeof x==='string')return asc?x.localeCompare(y):y.localeCompare(x);return asc?x-y:y-x;});}
var h='<table><thead><tr>'+COLS.map(function(c,i){return '<th data-i="'+i+'">'+c.t+'</th>';}).join('')+'</tr></thead><tbody>';
h+=rows.slice(0,LIM).map(function(r){return '<tr>'+COLS.map(function(c){return cell(r,c);}).join('')+'</tr>';}).join('');
h+='</tbody></table>';
if(rows.length>LIM)h+='<div class="hint">Показано '+LIM+' из '+rows.length+' строк. Уточните фильтр или смотрите Excel.</div>';
var el=document.getElementById(box);el.innerHTML=h;
el.querySelectorAll('th').forEach(function(th){th.onclick=function(){
var i=+th.dataset.i,k=COLS[i].k,s=ST[box];s.asc=(s.sortk===k)?!s.asc:false;s.sortk=k;
render(box,s.key,s.filt,s.sortk,s.asc);};});}
function wire(tabsId,boxId,inputId,initial){
if(!D[initial]){var ks=Object.keys(D);if(!ks.length)return;initial=ks[0];}
ST[boxId]={key:initial,filt:'',sortk:null,asc:false};
var tabs=document.getElementById(tabsId);
if(tabs)tabs.addEventListener('click',function(e){var b=e.target.closest('.tab');if(!b)return;
tabs.querySelectorAll('.tab').forEach(function(x){x.setAttribute('aria-selected',x===b?'true':'false');});
var s=ST[boxId];s.key=b.dataset.k;s.sortk=null;render(boxId,s.key,s.filt,null,false);});
var inp=inputId?document.getElementById(inputId):null;
if(inp)inp.addEventListener('input',function(){var s=ST[boxId];s.filt=inp.value;render(boxId,s.key,s.filt,s.sortk,s.asc);});
render(boxId,initial,'',null,false);}
wire('tabsH','tH','fH','l1');wire('tabsB','tB','fB','br');
wire('tabsW','tW','fW','w1');wire('tabsS','tS',null,'xyz');
</script></body></html>"""
