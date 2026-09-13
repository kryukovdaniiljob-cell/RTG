# -*- coding: utf-8 -*-
"""Сборка отчётов: Word, Excel, HTML-дашборд."""
from __future__ import annotations
import os, json
import numpy as np
import pandas as pd

# ------------------------------------------------------------------ формат
def млн(x):  return ("%.2f" % (x / 1e6)).replace(".", ",")
def цел(x):  return ("{:,.0f}".format(x)).replace(",", " ")
def пц(x, d=1):
    return (("%." + str(d) + "f") % x).replace(".", ",") if pd.notna(x) else "—"
def гм(x):   return пц(x, 2) if pd.notna(x) else "—"
def дн(x):
    return ("%.0f" % x) if pd.notna(x) and np.isfinite(x) and x < 100000 else "—"
def знак(v):
    return ("−" + млн(abs(v))) if v < 0 else млн(v)


def сводка(св, списки, oos, деф, cfg, период, лог=print) -> dict:
    ставка = float(cfg["экономика"]["ставка_хранения"]) + float(cfg["экономика"]["ставка_капитала"])
    порог = cfg["экономика"].get("порог_gmroi") or ставка
    l2 = св["L2_Направление"]
    S = {
        "дата": период["дата"].strftime("%d.%m.%Y"),
        "год": период["дата"].year,
        "дней": период["дней"],
        "ставка": ставка,
        "порог": порог,
        "sku": int(l2["SKU"].sum()),
        "оборот": float(l2["Оборот"].sum()),
        "вп": float(l2["ВП"].sum()),
        "запас": float(l2["Запас"].sum()),
        "запас_средний": float(l2["Запас_средний"].sum()),
        "маржа": 100 * float(l2["ВП"].sum()) / max(float(l2["Оборот"].sum()), 1),
        "gmroi": float(l2["ВП_год"].sum()) / max(float(l2["Запас_средний"].sum()), 1),
        "оборачиваемость": float(l2["Себест"].sum()) * period_ann(период) / max(float(l2["Запас_средний"].sum()), 1),
        "эконом_прибыль": float(l2["Эконом_прибыль"].sum()),
        "владение": float(l2["Владение"].sum()),
        "oos": 100 * float(oos["OOS"].sum()) / max(len(oos), 1),
        "упущено": float(деф["Lost_sales"].sum()),
        "dns": float(деф["DNS"].sum()),
        "коэф": float(cfg["дефицит"]["коэффициент_возврата_покупателя"]),
    }
    обсл = float(oos[oos.OOS == 0]["Кол"].sum())
    S["fill_rate"] = 100 * обсл / max(обсл + S["dns"], 1)
    S["csl"] = 100 * (1 - float(oos["OOS"].sum()) / max(len(oos), 1))
    S["oos_по_офисам"] = {str(i): [int(r.n), int(r.d), 100 * float(r.d) / max(r.n, 1)]
                          for i, r in oos.groupby("Офис").agg(n=("OOS", "size"), d=("OOS", "sum")).iterrows()}
    S["oos_по_месяцам"] = {str(i): 100 * float(r.d) / max(r.n, 1)
                           for i, r in oos.groupby("Месяц").agg(n=("OOS", "size"), d=("OOS", "sum")).iterrows()}
    в, м, р = списки["вывести"], списки["медленные"], списки["развивать"]
    mv = списки["переместить"]
    S["вывести"] = {"sku": len(в), "запас": float(в["Запас"].sum()), "владение": float(в["Владение"].sum())}
    S["медленные"] = {"sku": len(м), "запас": float(м["Запас"].sum()),
                      "владение": float(м["Владение"].sum()), "минус": float(м["Эконом_прибыль"].sum())}
    S["развивать"] = {"sku": len(р), "оборот": float(р["Оборот"].sum()),
                      "oos": float(р["OOS_%"].mean()) if len(р) else 0,
                      "маржа": float(р["Маржа_%"].mean()) if len(р) else 0}
    if len(mv):
        пересеч = set(mv["НС-Код"]) & (set(м["НС-Код"]) | set(в["НС-Код"]))
        дубль = float(mv[mv["НС-Код"].isin(пересеч)].groupby("НС-Код")["Стоимость_перемещ"].sum().sum())
        S["переместить"] = {"sku": int(mv["НС-Код"].nunique()),
                            "сумма": float(mv.groupby("НС-Код")["Стоимость_перемещ"].sum().sum()),
                            "дубль": дубль}
    else:
        S["переместить"] = {"sku": 0, "сумма": 0.0, "дубль": 0.0}
    S["высвобождение"] = (S["вывести"]["запас"] + S["медленные"]["запас"] / 2
                          + S["переместить"]["сумма"] - S["переместить"]["дубль"] / 2)
    S["экономия"] = S["вывести"]["владение"] + S["медленные"]["владение"] / 2
    плохие = l2[(l2["GMROI"] < порог) & l2["GMROI"].notna()]
    S["плохих_направлений"] = len(плохие)
    S["плохих_запас"] = float(плохие["Запас"].sum())
    S["плохих_убыток"] = float(плохие["Эконом_прибыль"].sum())
    return S


def period_ann(период):
    return 365.0 / период["дней"]


# ================================================================== EXCEL
МЕТРИКИ = [("SKU","n"),("SKU_активных","n"),("SKU_мёртвых","n"),("Оборот","n"),("Доля_оборота_%","p"),
           ("Себест","n"),("ВП","n"),("Маржа_%","p"),("Запас","n"),("Доля_запаса_%","p"),
           ("Запас_средний","n"),("Оборачиваемость","f"),("Дней_запаса","n"),("Дней_запаса_тек","n"),("GMROI","f"),
           ("Владение","n"),("Эконом_прибыль","n"),("Рент_запаса_%","p"),
           ("Засол","n"),("Засол_%","p"),("OOS_%","p"),("Упущено","n"),("Отрабатывает","t")]
ЗАГОЛОВКИ = {"SKU_активных":"SKU с продажами","SKU_мёртвых":"SKU без продаж","Доля_оборота_%":"Доля оборота",
             "Себест":"Себестоимость продаж","ВП":"Валовая прибыль","Маржа_%":"Маржа","Доля_запаса_%":"Доля запаса",
             "Запас":"Запас текущий","Запас_средний":"Запас средний","Оборачиваемость":"Оборачиваемость, раз/год",
             "Дней_запаса":"Дней запаса (по среднему)","Дней_запаса_тек":"Дней запаса (текущий остаток)","Владение":"Стоимость владения, ₽/год",
             "Эконом_прибыль":"Эконом. прибыль, ₽/год","Рент_запаса_%":"Рентабельность запаса",
             "Засол":"Засолы, ₽","Засол_%":"Доля засолов","OOS_%":"OOS","Упущено":"Упущено, ₽",
             "Отрабатывает":"Отрабатывает владение"}
ШИР = {"Группа планирования":22,"Товарное направление":30,"Группа 1":34,"Группа 2":34,"Группа 3":34,
       "Бренд":20,"Склад":44,"Офис":20,"Филиал":20,"Тип склада":14,"XYZ":16,"ABC":16,
       "Признак ликвидности":34,"Стратегия SKU":14,"НС-Код":13,"Название номенклатуры":50}

ЛИСТЫ = [
 ("01.Группа планирования","L1_Группа планирования",["Группа планирования"]),
 ("02.Направления","L2_Направление",["Группа планирования","Товарное направление"]),
 ("03.Группы 1","L3_Группа 1",["Группа планирования","Товарное направление","Группа 1"]),
 ("04.Группы 2","L4_Группа 2",["Товарное направление","Группа 1","Группа 2"]),
 ("05.Группы 3","L5_Группа 3",["Товарное направление","Группа 1","Группа 2","Группа 3"]),
 ("06.Бренды","B1_Бренд",["Бренд"]),
 ("07.Бренд x Направление","B2_Бренд x Направление",["Бренд","Товарное направление"]),
 ("08.Филиалы","W1_Филиал",["Филиал"]),
 ("09.Типы складов","W2_Тип склада",["Тип склада"]),
 ("10.Склады","W3_Склад",["Филиал","Офис","Склад","Тип склада"]),
 ("11.Направление x Склад","W4_Направление x Склад",["Товарное направление","Склад"]),
 ("12.Группа1 x Склад","W5_Группа1 x Склад",["Товарное направление","Группа 1","Склад"]),
 ("13.Бренд x Склад","W6_Бренд x Склад",["Бренд","Склад"]),
 ("14.Сегмент XYZ","S1_Сегмент XYZ",["XYZ"]),
 ("15.Ликвидность","S2_Ликвидность",["Признак ликвидности"]),
 ("16.Стратегия SKU","S3_Стратегия",["Стратегия SKU"]),
 ("17.ABC","S4_ABC",["ABC"]),
 ("18.SKU полный","L6_SKU",["НС-Код","Название номенклатуры","Бренд","Товарное направление",
                            "Группа 1","Группа 2","Группа 3","XYZ","ABC","Признак ликвидности"]),
]


def excel(путь, св, списки, S, cfg, лог=print):
    W = pd.ExcelWriter(путь, engine="xlsxwriter"); wb = W.book
    Fh = wb.add_format({"bold":True,"bg_color":"#1F3864","font_color":"white","border":1,"text_wrap":True,
                        "valign":"vcenter","align":"center","font_name":"Arial","font_size":9})
    Ft = wb.add_format({"font_name":"Arial","font_size":9})
    Fn = wb.add_format({"num_format":"#,##0","font_name":"Arial","font_size":9})
    F2 = wb.add_format({"num_format":"#,##0.00","font_name":"Arial","font_size":9})
    Fp = wb.add_format({"num_format":"0.0%","font_name":"Arial","font_size":9})
    Fb = wb.add_format({"bold":True,"font_name":"Arial","font_size":9})
    красный = wb.add_format({"bg_color":"#FFC7CE","font_color":"#9C0006","num_format":"#,##0.00","font_name":"Arial","font_size":9})
    зелёный = wb.add_format({"bg_color":"#C6EFCE","font_color":"#006100","num_format":"#,##0.00","font_name":"Arial","font_size":9})
    красныйN = wb.add_format({"font_color":"#9C0006","num_format":"#,##0","font_name":"Arial","font_size":9})
    порог = S["порог"]; хор = float(cfg["экономика"]["порог_gmroi_хороший"])

    # --- сводка
    rows = [("ДАННЫЕ",""),("Дата данных",S["дата"]),
            ("Период","01.01.%d – %s (%d дней)" % (S["год"], S["дата"], S["дней"])),
            ("",""),("ПЕРИМЕТР",""),
            ("SKU",S["sku"]),("Оборот, ₽",S["оборот"]),("Валовая прибыль, ₽",S["вп"]),
            ("Маржа",S["маржа"]/100),("Запас текущий, ₽",S["запас"]),("Запас средний, ₽",S["запас_средний"]),
            ("",""),("ЭФФЕКТИВНОСТЬ КАПИТАЛА",""),
            ("Ставка стоимости владения",S["ставка"]),("Порог GMROI",порог),
            ("GMROI периметра",S["gmroi"]),("Оборачиваемость, раз/год",S["оборачиваемость"]),
            ("Стоимость владения, ₽/год",S["владение"]),("Эконом. прибыль, ₽/год",S["эконом_прибыль"]),
            ("Направлений ниже порога",S["плохих_направлений"]),("Их запас, ₽",S["плохих_запас"]),
            ("",""),("ДЕФИЦИТ",""),
            ("OOS_incidence",S["oos"]/100),("Fill Rate",S["fill_rate"]/100),
            ("Cycle Service Level",S["csl"]/100),("DNS, ед.",S["dns"]),
            ("Упущенные продажи, ₽",S["упущено"]),
            ("",""),("ПОТЕНЦИАЛ",""),
            ("Высвобождение оборотных средств, ₽",S["высвобождение"]),
            ("Экономия содержания, ₽/год",S["экономия"]),
            ("Возврат упущенного оборота, ₽",S["упущено"])]
    pd.DataFrame(rows, columns=["Показатель","Значение"]).to_excel(W, sheet_name="00.Сводка", index=False, startrow=1, header=False)
    ws = W.sheets["00.Сводка"]
    ws.write(0,0,"Показатель",Fh); ws.write(0,1,"Значение",Fh)
    ws.set_column(0,0,44,Ft); ws.set_column(1,1,24,Ft)
    доли = ("Маржа","Ставка","Порог GMROI","OOS_incidence","Fill Rate","Cycle Service Level")
    for i,(k,v) in enumerate(rows):
        if v == "" and k: ws.write(i+1,0,k,Fb)
        elif isinstance(v,float) and k.startswith(доли): ws.write(i+1,1,v,Fp)
        elif isinstance(v,float) and ("GMROI" in k or "Оборачиваемость" in k): ws.write(i+1,1,v,F2)
        elif isinstance(v,(int,float)): ws.write(i+1,1,v,Fn)

    # --- уровни
    типы = {c:t for c,t in МЕТРИКИ}
    for имя, ключ, keys in ЛИСТЫ:
        if ключ not in св: continue
        d = св[ключ].copy()
        keys = [k for k in keys if k in d.columns]
        cols = keys + [c for c,_ in МЕТРИКИ if c in d.columns]
        out = d[cols].copy()
        for c,t in МЕТРИКИ:
            if c in out.columns and t == "p":
                out[c] = pd.to_numeric(out[c], errors="coerce")/100.0
        out.to_excel(W, sheet_name=имя, index=False, startrow=1, header=False)
        ws = W.sheets[имя]
        for j,c in enumerate(cols): ws.write(0,j,ЗАГОЛОВКИ.get(c,c),Fh)
        for j,c in enumerate(cols):
            t = типы.get(c,"t")
            if c in keys:   w,f = ШИР.get(c,30), Ft
            elif t=="p":    w,f = 10, Fp
            elif t=="f":    w,f = 11, F2
            elif t=="n":    w,f = 13, Fn
            else:           w,f = 12, Ft
            ws.set_column(j,j,w,f)
        ws.freeze_panes(1,len(keys)); ws.autofilter(0,0,len(out),len(cols)-1)
        if "GMROI" in cols:
            gi = cols.index("GMROI")
            ws.conditional_format(1,gi,len(out),gi,{"type":"cell","criteria":"<","value":порог,"format":красный})
            ws.conditional_format(1,gi,len(out),gi,{"type":"cell","criteria":">=","value":хор,"format":зелёный})
        if "Эконом_прибыль" in cols:
            ei = cols.index("Эконом_прибыль")
            ws.conditional_format(1,ei,len(out),ei,{"type":"cell","criteria":"<","value":0,"format":красныйN})

    # --- матрицы направление x склад
    if "W4_Направление x Склад" in св:
        w4 = св["W4_Направление x Склад"]
        порядок = w4.groupby("Склад")["Оборот"].sum().sort_values(ascending=False).index.tolist()
        for метрика, лист, fmt in [("GMROI","19.Матрица GMROI",F2),("Эконом_прибыль","20.Матрица эк.прибыли",Fn),
                                   ("Запас","21.Матрица запаса",Fn),("OOS_%","22.Матрица OOS",Fp)]:
            d = w4.copy()
            if метрика == "OOS_%": d[метрика] = d[метрика]/100.0
            p = d.pivot_table(index="Товарное направление", columns="Склад", values=метрика, aggfunc="sum")
            p = p.reindex([c for c in порядок if c in p.columns], axis=1)
            p.reset_index().to_excel(W, sheet_name=лист, index=False, startrow=1, header=False)
            ws = W.sheets[лист]
            hdr = ["Товарное направление"] + list(p.columns)
            for j,h in enumerate(hdr): ws.write(0,j,str(h),Fh)
            ws.set_column(0,0,32,Ft); ws.set_column(1,max(len(hdr)-1,1),17,fmt); ws.freeze_panes(1,1)
            if метрика == "GMROI":
                ws.conditional_format(1,1,len(p),len(hdr)-1,{"type":"cell","criteria":"<","value":порог,"format":красный})
            if метрика == "Эконом_прибыль":
                ws.conditional_format(1,1,len(p),len(hdr)-1,{"type":"cell","criteria":"<","value":0,"format":красныйN})

    # --- рабочие списки
    БАЗА = ["НС-Код","Название номенклатуры","Бренд","Товарное направление","Группа 1","Статус засола NEW",
            "ABC","XYZ","Оборот","ВП","Маржа_%","Запас","Запас_ед","Возраст","Дней_запаса_тек","GMROI",
            "Владение","Эконом_прибыль","OOS_%","Клиентов"]
    ПЕР = {"ВП":"Валовая прибыль","Маржа_%":"Маржа","Запас_ед":"Остаток, ед","Возраст":"Возраст запаса, дн",
           "Дней_запаса":"Дней запаса (по среднему)","Дней_запаса_тек":"Дней запаса (текущий остаток)","Владение":"Содержание, ₽/год","Эконом_прибыль":"Прибыль − содержание","OOS_%":"OOS"}
    ДЕНЬГИ = ("Оборот","Валовая прибыль","Запас","Остаток, ед","Возраст запаса, дн","Дней запаса",
              "Содержание, ₽/год","Прибыль − содержание","Клиентов")
    def список(лист, df):
        x = df[[c for c in БАЗА if c in df.columns]].rename(columns=ПЕР).copy()
        for c in ("Маржа","OOS"):
            if c in x.columns: x[c] = pd.to_numeric(x[c], errors="coerce")/100
        x.to_excel(W, sheet_name=лист, index=False, startrow=1, header=False)
        ws = W.sheets[лист]
        for j,c in enumerate(x.columns): ws.write(0,j,str(c),Fh)
        for j,c in enumerate(x.columns):
            if c in ("Маржа","OOS"):  ws.set_column(j,j,10,Fp)
            elif c == "GMROI":        ws.set_column(j,j,11,F2)
            elif c in ДЕНЬГИ:         ws.set_column(j,j,14,Fn)
            else:                     ws.set_column(j,j,ШИР.get(c,26),Ft)
        ws.freeze_panes(1,0); ws.autofilter(0,0,len(x),len(x.columns)-1)
    список("23.Вывести",   списки["вывести"])
    список("24.Медленные", списки["медленные"])
    список("25.Развивать", списки["развивать"])
    mv = списки["переместить"]
    if len(mv):
        mx = mv[["НС-Код","Название номенклатуры","Товарное направление","Офис_изб","Офис_деф",
                 "Можно_переместить","Стоимость_перемещ","Спрос","Кол"]].copy()
        mx.columns = ["НС-Код","Название номенклатуры","Направление","Откуда (лежит)","Куда (дефицит)",
                      "Переместить, ед","Сумма, ₽","Спрос, ед","Остаток, ед"]
        mx.to_excel(W, sheet_name="26.Переместить", index=False, startrow=1, header=False)
        ws = W.sheets["26.Переместить"]
        for j,c in enumerate(mx.columns): ws.write(0,j,c,Fh)
        for j,c in enumerate(mx.columns):
            ws.set_column(j,j,(14 if j>=5 else ШИР.get(c,26)),(Fn if j>=5 else Ft))
        ws.freeze_panes(1,0); ws.autofilter(0,0,len(mx),len(mx.columns)-1)
    W.close()
    import openpyxl
    wb2 = openpyxl.load_workbook(путь, read_only=True); n = len(wb2.sheetnames); wb2.close()
    лог("   Excel: %d листов, %.1f МБ" % (n, os.path.getsize(путь)/1048576))
    return путь
