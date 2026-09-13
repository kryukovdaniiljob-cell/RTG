# -*- coding: utf-8 -*-
"""Точка входа. Запускается двойным кликом по ЗАПУСТИТЬ.bat или GitHub Actions.

  python engine/run.py [--вход ПАПКА] [--без-архива]
"""
from __future__ import annotations
import os, sys, json, shutil, argparse, datetime as dt, traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import pandas as pd
import yaml

import io_excel, metrics, reports
from io_excel import ОшибкаДанных
from report_docx import word
from report_html import dashboard

КОРЕНЬ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ЖУРНАЛ: list[str] = []


def лог(msg=""):
    print(msg, flush=True)
    ЖУРНАЛ.append(str(msg))


def шапка(t):
    лог(""); лог("=" * 74); лог(t); лог("=" * 74)


# ------------------------------------------------------------ проверки качества
def проверки_качества(d, mine, факт, cfg):
    из_ = []
    c = cfg["проверки_качества"]
    sl = d["продажи"]
    sl = sl[sl["НС-Код"].isin(mine)]
    sym = sl[(sl["Продажи себ"] > float(c["символическая_цена_мин_себестоимость"])) &
             (sl["Оборот"] < float(c["символическая_цена_доля_оборота"]) * sl["Продажи себ"])]
    итог = {}
    if len(sym):
        итог["символические"] = {"строк": len(sym), "себестоимость": float(sym["Продажи себ"].sum()),
                                 "оборот": float(sym["Оборот"].sum()), "минус": float(sym["Продажи профит"].sum())}
        из_.append(["Продажи по символической цене (оборот ниже %d%% себестоимости)"
                    % int(100*float(c["символическая_цена_доля_оборота"])),
                    "%d строк" % len(sym), "Искажают маржу и GMROI по SKU и брендам"])
    cat = d["каталог"]
    rm = d.get("рабочая_матрица")
    if rm is not None and "Стратегия матрицы SKU" in rm.columns:
        rmap = dict(zip(rm["НС-Код"], rm["Стратегия матрицы SKU"]))
        cmap = dict(zip(cat["НС-Код"], cat.get("Стратегия SKU", pd.Series(dtype=object))))
        общие = set(rmap) & set(cmap)
        конфликт = [k for k in общие if str(rmap[k]).strip() and str(rmap[k]).strip() != str(cmap[k]).strip()]
        нет_в_кат = set(rmap) - set(cmap)
        if конфликт:
            из_.append(["Конфликт стратегии SKU: рабочая матрица против сквозной аналитики",
                        "%d SKU" % len(конфликт), "Сводные показывают устаревший статус"])
        if нет_в_кат:
            из_.append(["SKU рабочей матрицы отсутствуют в каталоге сквозной",
                        "%d SKU" % len(нет_в_кат), "Позиции выпадают из всех сводных"])
        итог["конфликт_стратегий"] = len(конфликт)
        итог["нет_в_каталоге"] = len(нет_в_кат)
    нормы = set(d["нормы"]["НС-Код"])
    складские = set(cat.loc[cat.get("Стратегия SKU", "").astype(str).eq("Складское") & cat["МОЁ"], "НС-Код"])
    без_норм = складские - нормы
    if без_норм:
        из_.append(["Складские SKU без норм в матрице пополнения",
                    "%d SKU" % len(без_норм), "Не попадают в расчёт пополнения и OOS"])
    if "Цена за ед.изм" in cat.columns:
        нули = int((cat.loc[cat["МОЁ"], "Цена за ед.изм"].fillna(0) <= 0).sum())
        if нули:
            из_.append(["Цена за ед. изм. в сквозной равна нулю", "%d SKU" % нули,
                        "Цены берутся из файла динамики стоков"])
    из_.append(["Нет дневной истории остатков", "—",
                "OOS считается помесячно; дневная точность появится за 2–3 недели накопления"])
    итог["проверки"] = из_
    return итог


# ------------------------------------------------------------ история
def копить_историю(d, mine, факт, cfg, дата):
    if not cfg["история"]["накапливать"]:
        return 0
    путь = os.path.join(КОРЕНЬ, "база", "история_стока.parquet")
    срез = факт.groupby(["НС-Код", "Склад"], as_index=False).agg(
        Запас=("Запас", "sum"), Запас_ед=("Запас_ед", "sum"))
    срез = срез[(срез["Запас"] != 0) | (срез["Запас_ед"] != 0)].copy()
    срез["Дата"] = pd.Timestamp(дата)
    if os.path.exists(путь):
        старое = pd.read_parquet(путь)
        старое = старое[старое["Дата"] != pd.Timestamp(дата)]
        срез = pd.concat([старое, срез], ignore_index=True)
    порог = pd.Timestamp(дата) - pd.Timedelta(days=int(cfg["история"]["хранить_дней"]))
    срез = срез[срез["Дата"] >= порог]
    os.makedirs(os.path.dirname(путь), exist_ok=True)
    срез.to_parquet(путь, index=False)
    дней = срез["Дата"].nunique()
    лог("   История стока: %d срезов, %d строк" % (дней, len(срез)))
    return дней


# ------------------------------------------------------------ ряды для графиков
def ряды_по_месяцам(d, mine, oos):
    МЕС = d["_месяцы"]
    sy = d["сток_год"]; sy = sy[sy["НС-Код"].isin(mine)]
    з = sy.groupby("Месяц")["Общая себ-ть запасов"].sum()
    sl = d["продажи"]; sl = sl[sl["НС-Код"].isin(mine)]
    о = sl.groupby("Месяц")["Оборот"].sum()
    oo = oos.groupby("Месяц").agg(n=("OOS", "size"), dd=("OOS", "sum"))
    return {"месяцы": МЕС,
            "запас":  [float(з.get(m, 0))/1e6 for m in МЕС],
            "оборот": [float(о.get(m, 0))/1e6 for m in МЕС],
            "oos":    [100*float(oo.dd.get(m, 0))/max(float(oo.n.get(m, 1)), 1) for m in МЕС]}


# ------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--вход", default=os.path.join(КОРЕНЬ, "1_ВХОД"))
    ap.add_argument("--без-архива", action="store_true")
    a = ap.parse_args()

    шапка("КАТЕГОРИЙНАЯ АНАЛИТИКА РТГ — запуск %s" % dt.datetime.now().strftime("%d.%m.%Y %H:%M"))
    cfg = yaml.safe_load(open(os.path.join(КОРЕНЬ, "config", "settings.yaml"), encoding="utf-8"))

    шапка("1. ПОИСК И РАСПОЗНАВАНИЕ ФАЙЛОВ")
    пути, замечания = io_excel.сканировать(a.вход)
    for z in замечания:
        лог("   ! " + z)
    if not пути:
        raise ОшибкаДанных(
            "В папке 1_ВХОД не найдено ни одной распознанной выгрузки." + chr(10) +
            "Положите туда файлы сквозной аналитики, динамики стоков, рабочей матрицы и юнит-экономики.")
    for к, p in пути.items():
        лог("   OK  %-14s <- %s" % (к, os.path.basename(p)))

    шапка("2. ЧТЕНИЕ ДАННЫХ")
    d = metrics.загрузить(пути, лог)
    d = metrics.подготовить(d, cfg, лог)
    mine = metrics.периметр(d, cfg, КОРЕНЬ, лог)

    шапка("3. РАСЧЁТ ДЕФИЦИТА (OOS)")
    oos, деф = metrics.считать_oos(d, mine, cfg, лог)

    шапка("4. ФАКТ-ТАБЛИЦА И СЕГМЕНТАЦИЯ")
    факт = metrics.построить_факт(d, mine, oos, деф, лог, int(cfg["дефицит"]["окно_спроса_месяцев"]))
    факт = metrics.разметить_сегменты(факт, cfg)

    шапка("5. СВЁРТКИ ПО ИЕРАРХИИ")
    св = metrics.все_свёртки(факт, cfg, d["_годовой"], d["_дней"], лог)

    шапка("6. РАБОЧИЕ СПИСКИ")
    списки = metrics.рабочие_списки(факт, св, cfg, d["_годовой"], лог)

    шапка("7. ПРОВЕРКИ КАЧЕСТВА ДАННЫХ")
    кач = проверки_качества(d, mine, факт, cfg)
    for p in кач["проверки"]:
        лог("   - %-62s %s" % (p[0][:62], p[1]))

    период = {"дата": d["_дата"], "дней": d["_дней"]}
    S = reports.сводка(св, списки, oos, деф, cfg, период, лог)
    S.update({k: v for k, v in кач.items() if k in ("символические", "проверки")})

    дата = d["_дата"].date()
    папка = os.path.join(КОРЕНЬ, "3_ОТЧЁТЫ", dt.date.today().isoformat())
    os.makedirs(папка, exist_ok=True)
    шапка("8. НАКОПЛЕНИЕ ИСТОРИИ")
    копить_историю(d, mine, факт, cfg, дата)

    шапка("9. СБОРКА ОТЧЁТОВ")
    сделано = []
    суф = дата.isoformat()
    if cfg["отчёты"]["excel"]:
        сделано.append(reports.excel(os.path.join(папка, "Расчёты_%s.xlsx" % суф), св, списки, S, cfg, лог))
    if cfg["отчёты"]["word"]:
        сделано.append(word(os.path.join(папка, "Аналитическая_записка_%s.docx" % суф), св, списки, S, cfg, лог))
    if cfg["отчёты"]["дашборд"]:
        ряды = ряды_по_месяцам(d, mine, oos)
        p = dashboard(os.path.join(папка, "Дашборд_%s.html" % суф), св, списки, S, cfg, ряды, лог)
        сделано.append(p)
        docs = os.path.join(КОРЕНЬ, "docs")
        os.makedirs(docs, exist_ok=True)
        shutil.copy(p, os.path.join(docs, "index.html"))
        лог("   Дашборд опубликован: docs/index.html")

    if not a.без_архива:
        шапка("10. АРХИВИРОВАНИЕ ИСХОДНИКОВ")
        арх = os.path.join(КОРЕНЬ, "2_АРХИВ", суф)
        os.makedirs(арх, exist_ok=True)
        for к, p in пути.items():
            цель = os.path.join(арх, os.path.basename(p))
            try:
                if os.path.exists(цель):
                    os.remove(цель)      # повторный расчёт за день заменяет архив
                shutil.move(p, цель)
                лог("   -> 2_АРХИВ/%s/%s" % (суф, os.path.basename(p)))
            except Exception as e:
                лог("   ! не удалось переместить %s: %s" % (os.path.basename(p), e))

    шапка("ГОТОВО")
    лог("Дата данных : %s" % S["дата"])
    лог("Периметр    : %s SKU, запас %s млн ₽, оборот %s млн ₽"
        % (reports.цел(S["sku"]), reports.млн(S["запас"]), reports.млн(S["оборот"])))
    лог("GMROI       : %s при пороге %s" % (reports.пц(S["gmroi"], 2), reports.пц(S["порог"], 2)))
    лог("OOS         : %s %%, упущено %s млн ₽" % (reports.пц(S["oos"]), reports.млн(S["упущено"])))
    лог("Потенциал   : высвободить %s млн ₽, экономия %s млн ₽/год"
        % (reports.млн(S["высвобождение"]), reports.млн(S["экономия"])))
    лог("")
    for f in сделано:
        лог("  " + os.path.relpath(f, КОРЕНЬ))

    json.dump(S, open(os.path.join(папка, "сводка.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1, default=str)
    open(os.path.join(папка, "журнал.txt"), "w", encoding="utf-8").write(chr(10).join(ЖУРНАЛ))
    return папка


if __name__ == "__main__":
    try:
        main()
    except ОшибкаДанных as e:
        print(""); print("!" * 74)
        print("РАСЧЁТ ОСТАНОВЛЕН"); print("!" * 74); print("")
        print(str(e)); print("")
        sys.exit(2)
    except Exception:
        print(""); print("!" * 74)
        print("НЕПРЕДВИДЕННАЯ ОШИБКА — покажите этот текст разработчику")
        print("!" * 74); print("")
        traceback.print_exc()
        sys.exit(1)
