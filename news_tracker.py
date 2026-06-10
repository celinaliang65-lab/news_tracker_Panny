import requests
import glob
import os
import json
import pandas as pd
import shioaji as sj
import time
import email.utils
from datetime import datetime, timedelta, timezone
from linebot import LineBotApi
from linebot.models import TextSendMessage, FlexSendMessage
import xml.etree.ElementTree as ET
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

# ── 設定區 ──────────────────────────────────────
LINE_ACCESS_TOKEN = os.environ.get('LINE_ACCESS_TOKEN', '').strip()
LINE_USER_ID = os.environ.get('LINE_USER_ID', '').strip()
SINOPAC_API_KEY = os.environ.get('SINOPAC_API_KEY', '').strip()
SINOPAC_SECRET_KEY = os.environ.get('SINOPAC_SECRET_KEY', '').strip()
FINMIND_TOKEN = os.environ.get('FINMIND_TOKEN', '').strip()
GOOGLE_CREDENTIALS = os.environ.get('GOOGLE_CREDENTIALS', '').strip()
SPREADSHEET_ID = os.environ.get('SPREADSHEET_ID', '').strip()

EXCLUDE_WORDS = ["爆料", "同學會", "達人", "無腦", "學堂", "康和", "券商分點", "存股","財神"]
THIN_LINE = "─────────────"

RANK_EMOJI = ["①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧", "⑨", "⑩",
              "⑪", "⑫", "⑬", "⑭", "⑮", "⑯", "⑰", "⑱", "⑲", "⑳",
              "㉑", "㉒", "㉓", "㉔", "㉕", "㉖", "㉗", "㉘", "㉙", "㉚",
              "㉛", "㉜", "㉝", "㉞", "㉟", "㊱", "㊲", "㊳", "㊴", "㊵",
              "㊶", "㊷", "㊸", "㊹", "㊺", "㊻", "㊼", "㊽", "㊾", "㊿"]

def get_gsheet_service():
    try:
        creds_dict = json.loads(GOOGLE_CREDENTIALS)
        creds = Credentials.from_service_account_info(
            creds_dict,
            scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
        return build("sheets", "v4", credentials=creds).spreadsheets()
    except Exception as e:
        print("gsheet service failed: " + str(e))
        return None

def read_sheet_as_df(service, sheet_name, id_col):
    result = service.values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=sheet_name
    ).execute()
    rows = result.get("values", [])
    if not rows:
        return pd.DataFrame()
    headers = rows[0]
    data = rows[1:]
    data = [r + [""] * (len(headers) - len(r)) for r in data]
    df = pd.DataFrame(data, columns=headers)
    df = df[df[id_col].str.strip() != ""]
    return df

def get_last_trading_day():
    now_tw = datetime.now(timezone(timedelta(hours=8)))
    weekday = now_tw.weekday()
    if weekday == 5:
        now_tw -= timedelta(days=1)
    elif weekday == 6:
        now_tw -= timedelta(days=2)
    return now_tw

def get_price_twse(sid):
    try:
        last_day = get_last_trading_day()
        date_str = last_day.strftime("%Y%m%d")
        url = f"https://www.twse.com.tw/exchangeReport/STOCK_DAY?response=json&date={date_str}&stockNo={sid}"
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=10)
        data = r.json()
        rows = data.get("data", [])
        if not rows:
            return None, None
        last = rows[-1]
        p = float(str(last[6]).replace(",", ""))
        chg = float(str(last[6]).replace(",", "")) - float(str(last[5]).replace(",", ""))
        return p, chg
    except Exception as e:
        print(f"TWSE failed {sid}: {e}")
        return None, None

def get_price_tpex(sid):
    try:
        last_day = get_last_trading_day()
        roc_year = last_day.year - 1911
        ym = f"{roc_year}/{last_day.strftime('%m')}"
        url = f"https://www.tpex.org.tw/web/stock/aftertrading/daily_trading_info/st43_result.php?l=zh-tw&d={ym}&s={sid}&o=json"
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=10)
        data = r.json()
        rows = data.get("aaData", [])
        if not rows:
            return None, None
        last = rows[-1]
        p = float(str(last[6]).replace(",", ""))
        prev = float(str(last[5]).replace(",", "")) if last[5] != "--" else p
        chg = round(p - prev, 2)
        return p, chg
    except Exception as e:
        print(f"TPEX failed {sid}: {e}")
        return None, None

def get_price_shioaji(api, sid):
    try:
        try:
            c = api.Contracts.Stocks[sid]
        except:
            c = api.Contracts.Stocks.OTC[sid]
        if c is None:
            return None, None
        snap = api.snapshots([c])[0]
        p = float(snap.close) if snap.close else None
        try:
            chg = float(snap.change_price)
        except:
            chg = None
        return p, chg
    except Exception as e:
        print(f"shioaji failed {sid}: {e}")
        return None, None

def get_price(api, sid, exchange):
    if api:
        p, chg = get_price_shioaji(api, sid)
        if p and p > 0:
            return p, chg
    if exchange == "OTC":
        p, chg = get_price_tpex(sid)
    else:
        p, chg = get_price_twse(sid)
    return p, chg

def get_monthly_revenue(sid):
    try:
        now_tw = datetime.now(timezone(timedelta(hours=8)))
        start_date = (now_tw - timedelta(days=120)).strftime("%Y-%m-%d")
        params = {
            "dataset": "TaiwanStockMonthRevenue",
            "data_id": sid,
            "start_date": start_date,
        }
        if FINMIND_TOKEN:
            params["token"] = FINMIND_TOKEN
        r = requests.get("https://api.finmindtrade.com/api/v4/data", params=params, timeout=15)
        data = r.json().get("data", [])
        if not data:
            return None, None, None
        enriched = []
        for d in data:
            pub_year = int(d["date"][:4])
            pub_month = int(d["date"][5:7])
            pub_day = int(d["date"][8:10])
            pub_dt = datetime(pub_year, pub_month, pub_day, tzinfo=timezone(timedelta(hours=8)))
            if datetime.now(timezone(timedelta(hours=8))) < pub_dt:
                continue
            actual_month = pub_month - 1
            actual_year = pub_year
            if actual_month == 0:
                actual_month = 12
                actual_year -= 1
            enriched.append({
                "actual_year": actual_year,
                "actual_month": actual_month,
                "revenue": d["revenue"],
                "month_str": f"{actual_year}-{actual_month:02d}",
            })
        if not enriched:
            return None, None, None
        enriched.sort(key=lambda x: (x["actual_year"], x["actual_month"]))
        last = enriched[-1]
        prev = enriched[-2] if len(enriched) >= 2 else None
        revenue = last["revenue"] / 1e8
        month_str = last["month_str"]
        if prev and prev["revenue"]:
            mom = (last["revenue"] - prev["revenue"]) / prev["revenue"] * 100
        else:
            mom = 0.0
        return month_str, revenue, mom
    except Exception as e:
        print(f"revenue failed {sid}: {e}")
        return None, None, None

def get_eps(sid):
    try:
        now_tw = datetime.now(timezone(timedelta(hours=8)))
        start_date = (now_tw - timedelta(days=180)).strftime("%Y-%m-%d")
        params = {
            "dataset": "TaiwanStockFinancialStatements",
            "data_id": sid,
            "start_date": start_date,
        }
        if FINMIND_TOKEN:
            params["token"] = FINMIND_TOKEN
        r = requests.get("https://api.finmindtrade.com/api/v4/data", params=params, timeout=15)
        rows = r.json().get("data", [])
        if not rows:
            return None, None
        eps_rows = [row for row in rows if row.get("type") == "EPS"]
        if not eps_rows:
            return None, None
        last = eps_rows[-1]
        date_str = last["date"]
        year = int(date_str[:4])
        month = int(date_str[5:7])
        quarter_map = {3: "1", 6: "2", 9: "3", 12: "4"}
        q_num = quarter_map.get(month, "?")
        yy = str(year)[-2:]
        quarter = f"{q_num}Q{yy}"
        eps = float(last["value"])
        return quarter, eps
    except Exception as e:
        print(f"EPS failed {sid}: {e}")
        return None, None

def get_news(stock_name, stock_id, max_news=2):
    try:
        query = f"{stock_name} {stock_id}"
        url = f"https://news.google.com/rss/search?q={query}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=10)
        root = ET.fromstring(r.content)
        items = root.findall(".//item")
        news_list = []
        now_tw = datetime.now(timezone(timedelta(hours=8)))
        for item in items:
            if len(news_list) >= max_news:
                break
            try:
                pub_date_str = item.find("pubDate").text
                pub_date = email.utils.parsedate_to_datetime(pub_date_str)
                age_hours = (now_tw - pub_date.astimezone(timezone(timedelta(hours=8)))).total_seconds() / 3600
                if age_hours > 48:
                    continue
            except:
                continue
            title = item.find("title").text
            if not title:
                continue
            if " - " in title:
                title = title.rsplit(" - ", 1)[0]
            title = title.strip()
            if any(word in title for word in EXCLUDE_WORDS):
                continue
            if len(title) > 25:
                title = title[:25] + "..."
            news_list.append(title)
        return news_list
    except Exception as e:
        print(f"news failed {stock_id}: {e}")
        return []

# ── 大盤資訊 ──────────────────────────────────────

def get_market_info(api=None):
    try:
        if api:
            try:
                c = api.Contracts.Indices.TSE["TAIEX"]
                snap = api.snapshots([c])[0]
                close = float(snap.close) if snap.close else None
                chg = float(snap.change_price) if snap.change_price else None
                chg_pct = float(snap.change_rate) if snap.change_rate else None
                if close and close > 0:
                    print(f"market from shioaji: {close} {chg} {chg_pct}")
                    return close, chg, chg_pct
            except Exception as e:
                print(f"shioaji market failed: {e}")
        url = "https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch=tse_t00.tw"
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=10)
        data = r.json()
        msg = data.get("msgArray", [])
        if msg:
            item = msg[0]
            close_raw = str(item.get("z", "")).strip()
            prev_raw = str(item.get("y", "")).strip()
            if close_raw == "-" or not close_raw:
                close_raw = str(item.get("pz", "")).strip()
            if close_raw and close_raw != "-" and prev_raw and prev_raw != "-":
                close = float(close_raw)
                prev = float(prev_raw)
                chg = round(close - prev, 2)
                chg_pct = round(chg / prev * 100, 2) if prev else 0
                print(f"market from twse mis: {close} {chg} {chg_pct}")
                return close, chg, chg_pct
        return None, None, None
    except Exception as e:
        print(f"market info failed: {e}")
        return None, None, None

def get_market_news(max_news=2):
    try:
        url = "https://news.google.com/rss/search?q=台股+大盤+今日&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=10)
        root = ET.fromstring(r.content)
        items = root.findall(".//item")
        news_list = []
        now_tw = datetime.now(timezone(timedelta(hours=8)))
        for item in items:
            if len(news_list) >= max_news:
                break
            try:
                pub_date_str = item.find("pubDate").text
                pub_date = email.utils.parsedate_to_datetime(pub_date_str)
                age_hours = (now_tw - pub_date.astimezone(timezone(timedelta(hours=8)))).total_seconds() / 3600
                if age_hours > 48:
                    continue
            except:
                continue
            title = item.find("title").text
            if not title:
                continue
            if " - " in title:
                title = title.rsplit(" - ", 1)[0]
            title = title.strip()
            if len(title) > 40:
                title = title[:40] + "..."
            news_list.append(title)
        return news_list
    except Exception as e:
        print(f"market news failed: {e}")
        return []

# ── Flex Message 漲幅排行卡片（透明石綠） ────────────────────────

def build_flex_leaderboard(growth_list, now_tw, market_close=None, market_chg=None, market_chg_pct=None, market_news=None):
    COLOR_HEADER  = "#7a9688"
    COLOR_TITLE   = "#eef4f1"
    COLOR_SUB     = "#c0d4ca"
    COLOR_PCT_POS = "#3d6655"
    COLOR_PCT_NEG = "#6b8878"
    COLOR_RANK    = "#aaaaaa"
    COLOR_NAME    = "#333333"
    COLOR_FOOT    = "#a8c0b8"
    COLOR_NOTE    = "#a8c0b8"
    COLOR_DIV     = "#dceae4"

    rows = []
    for i, item in enumerate(growth_list):
        sign_str = "+" if item["growth"] >= 0 else "-"
        abs_pct = "{:.2f}".format(abs(item["growth"]))
        pct_text = f"{sign_str}{abs_pct}%"
        pct_color = COLOR_PCT_POS if item["growth"] >= 0 else COLOR_PCT_NEG
        rank_str = RANK_EMOJI[i] if i < len(RANK_EMOJI) else str(i + 1)
        hold = str(item.get("hold", "")).strip()

        if hold == "★":
            name_text = "★ " + item["sid"] + " " + item["name"]
        elif hold == "☆":
            name_text = "☆ " + item["sid"] + " " + item["name"]
        else:
            name_text = "　 " + item["sid"] + " " + item["name"]

        rows.append({
            "type": "box",
            "layout": "horizontal",
            "contents": [
                {"type": "text", "text": rank_str,   "size": "sm", "color": COLOR_RANK, "flex": 1},
                {"type": "text", "text": pct_text,   "size": "sm", "color": pct_color,  "flex": 3, "weight": "bold"},
                {"type": "text", "text": name_text,  "size": "sm", "color": COLOR_NAME, "flex": 6, "wrap": True},
            ],
            "paddingTop": "4px",
            "paddingBottom": "4px",
        })

    date_str = now_tw[:10]
    time_str = now_tw[11:] if len(now_tw) > 10 else ""

    return {
        "type": "bubble",
        "size": "giga",
        "header": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": COLOR_HEADER,
            "paddingAll": "12px",
            "contents": [
                {
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {"type": "text", "text": "📊 漲幅排行", "size": "sm", "weight": "bold", "color": COLOR_TITLE, "flex": 0},
                        {"type": "text", "text": date_str, "size": "xs", "color": COLOR_SUB, "align": "end", "flex": 1, "gravity": "center"},
                    ]
                },
                {"type": "text", "text": "自 2/26 起成長幅度分析 (%)", "size": "xs", "color": COLOR_SUB, "margin": "sm"},
            ]
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": "#f6faf8",
            "paddingAll": "12px",
            "spacing": "none",
            "contents": [
                # ── 大盤資訊區塊 ──
                *([
                    {
                        "type": "box",
                        "layout": "vertical",
                        "backgroundColor": "#e8f4f0",
                        "cornerRadius": "8px",
                        "paddingAll": "8px",
                        "margin": "none",
                        "contents": [
                            {"type": "text", "text": "📈 加權指數 {:.2f}".format(market_close),
                             "size": "xs", "weight": "bold", "color": "#3d6655"},
                            {"type": "text",
                             "text": "{} {:+.2f}（{:+.2f}%）".format("🔺" if market_chg >= 0 else "🔻", market_chg, market_chg_pct),
                             "size": "xs", "color": "#d93025" if market_chg >= 0 else "#1a73e8", "margin": "xs"},
                            *([{"type": "text", "text": "・" + n, "size": "xxs", "color": "#6b8878", "margin": "xs", "wrap": True} for n in (market_news or [])]),
                        ]
                    },
                    {"type": "separator", "margin": "sm", "color": COLOR_DIV},
                ] if market_close is not None else []),
                *rows,
                {"type": "separator", "margin": "sm", "color": COLOR_DIV},
                {"type": "text", "text": "符號說明：★ 已持有股票　☆ 推薦購買股票", "size": "xxs", "color": COLOR_NOTE, "margin": "sm", "wrap": True},
                {"type": "text", "text": "麗卿 · " + time_str, "size": "xxs", "color": COLOR_FOOT, "align": "end", "margin": "xs"},
            ]
        }
    }


def job():
    print("connecting to Google Sheets...")
    service = get_gsheet_service()
    if not service:
        print("Google Sheets connection failed")
        return

    df_watch = read_sheet_as_df(service, "觀察清單", "代號")
    print("sheets loaded: watch=" + str(len(df_watch)))

    now_tw = datetime.now(timezone(timedelta(hours=8))).strftime("%Y/%m/%d %H:%M")

    api = sj.Shioaji()
    try:
        api.login(api_key=SINOPAC_API_KEY, secret_key=SINOPAC_SECRET_KEY)
        time.sleep(3)
        print("shioaji logged in")
    except Exception as e:
        print(f"shioaji login failed: {e}")
        api = None

    # ── 第一步：收集股價和漲幅 ──
    watch_data = []
    growth_list = []

    for _, row in df_watch.iterrows():
        sid = str(row["代號"]).strip()
        name = str(row["名稱"]).strip()
        exchange = str(row.get("交易所", "TSE")).strip()
        cost_226 = float(str(row["2026/2/26收盤價"]).replace(",", ""))
        hold = str(row.get("持有股票", "")).strip()
        print(f"fetching watch: {sid} ({exchange})")

        p, chg = get_price(api, sid, exchange)

        growth = None
        if p is not None and p > 0 and cost_226 > 0:
            growth = (p - cost_226) / cost_226 * 100
            growth_list.append({"sid": sid, "name": name, "growth": growth, "hold": hold})

        watch_data.append({
            "sid": sid, "name": name, "exchange": exchange,
            "cost_226": cost_226, "p": p, "chg": chg, "growth": growth,
        })

    # ── 第二步：Flex Message 推播 ──
    growth_list.sort(key=lambda x: x["growth"], reverse=True)
    line_api = LineBotApi(LINE_ACCESS_TOKEN)
    market_close, market_chg, market_chg_pct = get_market_info(api)
    market_news = get_market_news()
    flex_body = build_flex_leaderboard(growth_list, now_tw, market_close, market_chg, market_chg_pct, market_news)
    flex_msg = FlexSendMessage(alt_text="📊 自 2/26 起成長幅度分析 (%)", contents=flex_body)
    try:
        line_api.push_message(LINE_USER_ID, flex_msg)
        print("leaderboard flex sent!")
    except Exception as e:
        print(f"LINE flex failed: {e}")

    # ── 第三步：純文字報告（完全維持原本） ──
    report = f"📰 觀察清單新聞摘要\n      {now_tw}\n"
    report += "━━━━━━━━━━━━━\n"

    for d in watch_data:
        sid = d["sid"]
        name = d["name"]
        p = d["p"]
        chg = d["chg"]
        growth = d["growth"]
        cost_226 = d["cost_226"]

        report += f"\n{sid} {name}\n"

        if p is not None and p > 0:
            if chg is not None and chg > 0:
                day_str = f"🔺 +{chg:.2f}"
            elif chg is not None and chg < 0:
                day_str = f"🔽 {chg:.2f}"
            else:
                day_str = "➖ 0.00"
            report += f"  現價：{p:.2f}  {day_str}\n"
        else:
            report += "  價格取得失敗\n"

        month_str, revenue, mom = get_monthly_revenue(sid)
        if month_str and revenue is not None:
            mom_sign = "+" if mom >= 0 else ""
            mom_arrow = "↑" if mom >= 0 else "↓"
            report += f"  月營收：{month_str}  {revenue:.1f}億  {mom_arrow} {mom_sign}{mom:.1f}%MoM\n"

        quarter, eps = get_eps(sid)
        if quarter and eps:
            report += f"  EPS：{quarter}  {eps:.2f}元\n"

        news_list = get_news(name, sid)
        report += THIN_LINE + "\n"
        if news_list:
            for news in news_list:
                report += f"  ・{news}\n"
        else:
            report += "  暫無最新新聞\n"

    report += "\n━━━━━━━━━━━━━"

    try:
        line_api.push_message(LINE_USER_ID, TextSendMessage(text=report))
        print("news sent!")
    except Exception as e:
        print(f"LINE failed: {e}")
    finally:
        if api:
            try:
                api.logout()
            except:
                pass

if __name__ == "__main__":
    job()
