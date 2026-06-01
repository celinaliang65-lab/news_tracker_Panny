# 姊姊（麗卿）股票追蹤系統說明 v1.0
## 更新日期：2026/05/30

---

## 一、系統概覽

| 項目 | 說明 |
|------|------|
| 推播人數 | 單人（LINE_USER_ID） |
| 配色 | 透明石綠（#7a9688） |
| 推播時間 | 週一至週五（cron 依 news.yml 設定） |
| 程式檔案 | news_tracker.py |

---

## 二、推播內容

### 訊息① Flex Message 漲幅排行卡片

```
┌─────────────────────────────────┐
│ 📊 漲幅排行          2026/05/30  │ ← 透明石綠 #7a9688
│ 自 2/26 起成長幅度分析 (%)       │
├─────────────────────────────────┤  淺綠白底 #f6faf8
│ 📈 加權指數 44732.94             │
│ 🔺 +1096.50（+2.51%）           │
│ ・台股史詩巨震...                │
│ ─────────────────────────────── │
│ ① +82.20%  ★ 2049 上銀         │
│ ② +60.14%  　 2308 台達電       │
│ ③ +15.04%  ★ 2330 台積電       │
│ ...                              │
│ ─────────────────────────────── │
│ 符號說明：★ 已持有股票　☆ 推薦購買股票 │
│                      麗卿 · 15:00│
└─────────────────────────────────┘
```

### 訊息② 純文字觀察清單新聞摘要

```
📰 觀察清單新聞摘要
      2026/05/30 15:00
━━━━━━━━━━━━━

2308 台達電
  現價：2445.00  🔺 +55.00
  月營收：2026-04  586.9億  ↓ -1.8%MoM
  EPS：1Q26  7.91元
  💰除息：2026/06/17 現金股利：11.60元
─────────────
  ・台達電股東會》不只看好AI！...
  ・台達電：AI趨勢非常好...
```

---

## 三、Google Sheets 設定

| 項目 | 說明 |
|------|------|
| SPREADSHEET_ID | 從 GitHub Secrets 讀取 |
| Sheet tab | 觀察清單 |

### 觀察清單欄位

| 欄位 | 說明 |
|------|------|
| 名稱 | 股票中文名稱 |
| 交易所 | TSE 或 OTC |
| 代號 | 股票代號 |
| 持有股票 | ★（已持有）/ ☆（推薦）/ 空白 |
| 2026/2/26收盤價 | 漲幅計算基準 |

> Service Account：`stock-tracker-bot@stock-tracker-496215.iam.gserviceaccount.com` → 編輯者

---

## 四、GitHub Secrets 設定

| Secret 名稱 | 說明 | 必/選填 |
|------------|------|---------|
| LINE_ACCESS_TOKEN | LINE Bot Channel Access Token | 必填 |
| LINE_USER_ID | 麗卿本人 LINE User ID | 必填 |
| SINOPAC_API_KEY | 永豐金 API Key | 必填 |
| SINOPAC_SECRET_KEY | 永豐金 Secret Key | 必填 |
| GOOGLE_CREDENTIALS | Service Account JSON 憑證 | 必填 |
| SPREADSHEET_ID | Google Sheets ID | 必填 |
| FINMIND_TOKEN | FinMind API Token | 選填 |

---

## 五、加權指數資料來源

優先順序：
1. **永豐金 Shioaji** — `api.Contracts.Indices.TSE["TAIEX"]`
2. **TWSE 即時 API** — `mis.twse.com.tw`（盤中用 `z`，盤後用 `pz`）

---

## 六、配息資料來源

從 TWSE API 自動抓取未來 180 天內的配息：
`https://www.twse.com.tw/rwd/zh/exRight/TWT48U`

有配息才顯示，無配息不顯示。

---

## 七、月營收 / EPS 資料來源

FinMind API：
- 月營收：`TaiwanStockMonthRevenue`
- EPS：`TaiwanStockFinancialStatements`

設定 `FINMIND_TOKEN` Secret 可提高 API 配額。

---

## 八、推播排程

| 檔案 | cron | 台灣時間 |
|------|------|---------|
| news_tracker.py | 依 news.yml 設定 | 週一至週五 |

---

## 九、符號說明

| 符號 | 說明 |
|------|------|
| ★ | 已持有股票 |
| ☆ | 推薦購買股票 |
| 空白 | 全形空白佔位，代號整齊對齊 |

---

## 十、變更紀錄

| 日期 | 版本 | 說明 |
|------|------|------|
| 2026-05-25 | v0.9 | 初始版本：透明石綠配色、持有符號、Flex 排行、月營收/EPS/新聞/配息 |
| 2026-05-30 | v1.0 | 加入加權指數大盤區塊（Shioaji 優先，TWSE 即時 API 備用，盤後用 pz） |

---

*建立者：Claude (Anthropic)　更新日期：2026/05/30*
