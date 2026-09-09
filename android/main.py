
import os, json, math, threading, time
import requests, certifi

from kivy.app import App
from kivy.clock import Clock
from kivy.lang import Builder
from kivy.properties import StringProperty, BooleanProperty
from kivy.uix.boxlayout import BoxLayout

APP_DIR = os.path.dirname(os.path.abspath(__file__))
TICKER_FILE = os.path.join(APP_DIR, "tickers_bist.txt")

TV_URL = "https://scanner.tradingview.com/turkey/scan"

COLUMNS = [
    "name",
    "close",
    "RSI",
    "MACD.macd",
    "MACD.signal",
    "EMA20",
    "EMA50",
    "EMA200",
    "ATR",
    "volume",
    "average_volume_10d_calc",
    "Perf.1M",
    "Perf.3M",
    "Perf.6M",
    "Perf.Y",
    "price_52_week_high",
    "price_52_week_low",
    "Recommend.All",
]

KV = r"""
#:import dp kivy.metrics.dp

<RootView>:
    orientation: "vertical"
    padding: dp(10)
    spacing: dp(7)

    Label:
        text: "[b]QUANT SCANNER MOBILE[/b]"
        markup: True
        size_hint_y: None
        height: dp(38)
        font_size: "20sp"

    Label:
        text: "Bağımsız Android • TradingView tarama kaynağı"
        size_hint_y: None
        height: dp(28)
        font_size: "13sp"

    BoxLayout:
        size_hint_y: None
        height: dp(48)
        spacing: dp(6)

        Button:
            text: "BAĞLANTI TESTİ"
            size_hint_x: .34
            disabled: root.scanning
            on_release: root.test_connection()

        Button:
            text: "PİYASAYI TARA"
            disabled: root.scanning
            on_release: root.start_scan()

        Button:
            text: "İPTAL"
            size_hint_x: .22
            disabled: not root.scanning
            on_release: root.cancel_scan()

    Label:
        text: root.status
        size_hint_y: None
        height: dp(54)
        text_size: self.width, None
        halign: "center"

    BoxLayout:
        size_hint_y: None
        height: dp(44)
        spacing: dp(4)
        Button:
            text: "En Güçlü"
            on_release: root.show_group("top")
        Button:
            text: "Dip"
            on_release: root.show_group("dip")
        Button:
            text: "Geçmiş"
            on_release: root.show_group("history")
        Button:
            text: "Risk"
            on_release: root.show_group("risk")

    ScrollView:
        do_scroll_x: False
        Label:
            text: root.result_text
            markup: True
            text_size: self.width - dp(12), None
            size_hint_y: None
            height: max(self.texture_size[1] + dp(30), self.parent.height)
            valign: "top"
"""

def fnum(v, default=0.0):
    try:
        x = float(v)
        return x if math.isfinite(x) else default
    except Exception:
        return default

def load_tickers():
    with open(TICKER_FILE, "r", encoding="utf-8", errors="ignore") as f:
        out = []
        for line in f:
            s = line.strip().upper().replace(".IS", "")
            if s and not s.startswith("#"):
                out.append(s)
        return list(dict.fromkeys(out))

def tv_headers():
    return {
        "User-Agent": "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36",
        "Accept": "text/plain, */*; q=0.01",
        "Content-Type": "application/json",
        "Origin": "https://www.tradingview.com",
        "Referer": "https://www.tradingview.com/",
        "Connection": "close",
    }

def tv_scan_symbols(symbols):
    payload = {
        "symbols": {"tickers": ["BIST:" + s for s in symbols]},
        "columns": COLUMNS,
        "range": [0, len(symbols)],
    }
    r = requests.post(
        TV_URL,
        headers=tv_headers(),
        json=payload,
        timeout=25,
        verify=certifi.where(),
    )
    if r.status_code == 429:
        raise RuntimeError("HTTP 429 - TradingView hız sınırı")
    if r.status_code >= 400:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:120]}")
    data = r.json()
    rows = data.get("data") or []
    return rows

def row_to_dict(row):
    d = row.get("d") or []
    if len(d) < len(COLUMNS):
        d = d + [None] * (len(COLUMNS)-len(d))
    x = dict(zip(COLUMNS, d))
    s = row.get("s") or ""
    x["symbol"] = s.split(":")[-1] if ":" in s else s
    return x

def score_row(x):
    price = fnum(x["close"])
    rsi = fnum(x["RSI"], 50)
    macd = fnum(x["MACD.macd"])
    macds = fnum(x["MACD.signal"])
    e20 = fnum(x["EMA20"])
    e50 = fnum(x["EMA50"])
    e200 = fnum(x["EMA200"])
    atr = fnum(x["ATR"])
    vol = fnum(x["volume"])
    avgv = fnum(x["average_volume_10d_calc"])
    p1 = fnum(x["Perf.1M"])
    p3 = fnum(x["Perf.3M"])
    p6 = fnum(x["Perf.6M"])
    py = fnum(x["Perf.Y"])
    hi52 = fnum(x["price_52_week_high"])
    lo52 = fnum(x["price_52_week_low"])
    rec = fnum(x["Recommend.All"])

    volr = vol/avgv if avgv > 0 else 1.0
    atrp = atr/price*100 if price > 0 else 0
    dd52 = (price/hi52-1)*100 if hi52 > 0 else 0
    dipdist = (price/lo52-1)*100 if lo52 > 0 else 999

    score = 0
    why = []
    def add(cond, pts, txt):
        nonlocal score
        if cond:
            score += pts
            why.append(txt)

    add(price > e20 > 0, 8, "EMA20 üstü")
    add(price > e50 > 0, 10, "EMA50 üstü")
    add(price > e200 > 0, 12, "EMA200 üstü")
    add(e20 > e50 > 0, 8, "20>50")
    add(e50 > e200 > 0, 10, "50>200")
    add(macd > macds, 8, "MACD+")
    add(50 <= rsi <= 68, 8, "RSI dengeli")
    add(p1 > 0, 5, "1A+")
    add(p3 > 0, 6, "3A+")
    add(p6 > 0, 4, "6A+")
    add(volr >= 1.2, 6, "Hacim+")
    add(rec >= 0.3, 7, "TV teknik olumlu")

    if rsi > 75: score -= 10
    if atrp > 6: score -= 7
    if dd52 < -30: score -= 5
    score = max(0, min(100, int(round(score))))

    if rsi >= 76:
        phase = "AŞIRI ISINMIŞ"
    elif price > e20 > e50 > e200 > 0 and rsi >= 50:
        phase = "GÜÇLÜ TREND"
    elif price > e200 > 0 and e20 > e50 > 0 and 45 <= rsi <= 62:
        phase = "ERKEN / DÖNÜŞ"
    elif e200 > 0 and price < e200:
        phase = "ZAYIF TREND"
    else:
        phase = "KARMA"

    dip = 0
    conf = 0
    dipwhy = []
    if dipdist <= 6:
        dip += 35; dipwhy.append("52H dibe çok yakın")
    elif dipdist <= 12:
        dip += 25; dipwhy.append("52H dibe yakın")
    elif dipdist <= 20:
        dip += 12
    if 35 <= rsi <= 55:
        dip += 15; conf += 1; dipwhy.append("RSI toparlanma")
    if macd > macds:
        dip += 15; conf += 1; dipwhy.append("MACD pozitif")
    if price > e20 > 0:
        dip += 15; conf += 1; dipwhy.append("EMA20 üstü")
    if volr >= 1.2:
        dip += 10; conf += 1; dipwhy.append("Hacim teyidi")
    if p1 > 0:
        dip += 10; conf += 1; dipwhy.append("1A pozitif")
    if phase == "ZAYIF TREND": dip -= 15
    if p3 < -20: dip -= 10
    if atrp > 7: dip -= 10
    dip = max(0, min(100, int(dip)))
    dipdur = "DÖNÜŞ ADAYI" if dip >= 70 and conf >= 3 else "BEKLE / TEYİT" if dip >= 50 else "ZAYIF"

    risk = 0
    riskwhy = []
    if atrp >= 8:
        risk += 30; riskwhy.append("ATR çok yüksek")
    elif atrp >= 6:
        risk += 18
    if rsi >= 82:
        risk += 25; riskwhy.append("RSI aşırı")
    elif rsi >= 75:
        risk += 12
    if p1 < -10: risk += 15
    if p3 < -20: risk += 15
    if rec <= -0.3: risk += 15
    if phase == "AŞIRI ISINMIŞ": risk += 20
    risk = max(0, min(100, int(risk)))
    protect = "ALMA" if risk >= 65 else "BEKLE" if risk >= 40 else "ADAY"

    history_score = 50
    history_score += 12 if p1 > 0 else -8
    history_score += 15 if p3 > 0 else -10
    history_score += 10 if p6 > 0 else -6
    history_score += 8 if py > 0 else -5
    history_score = max(0, min(100, int(history_score)))
    history_grade = "GÜÇLÜ" if history_score >= 75 else "ORTA" if history_score >= 55 else "ZAYIF"

    overall = int(round(score*0.82 + dip*0.10 + history_score*0.08))
    if protect == "ALMA":
        final = "UZAK DUR / YÜKSEK RİSK"
    elif overall >= 72 and score >= 65:
        final = "GÜÇLÜ ADAY"
    elif overall >= 60:
        final = "İZLE"
    else:
        final = "KARMA / BEKLE"

    return {
        "Varlik": x["symbol"],
        "Fiyat": round(price, 2),
        "TeknikPuan": score,
        "GenelPuan": overall,
        "NihaiKarar": final,
        "Evre": phase,
        "RSI": round(rsi, 1),
        "ATR%": round(atrp, 2),
        "HacimOran": round(volr, 2),
        "1Ay%": round(p1, 2),
        "3Ay%": round(p3, 2),
        "6Ay%": round(p6, 2),
        "1Yil%": round(py, 2),
        "52H_Zirve_Uzaklik%": round(dd52, 2),
        "DipPuan": dip,
        "DipDurum": dipdur,
        "DiptenUzaklik%": round(dipdist, 2),
        "DipTeyitSayisi": conf,
        "DipNeden": "; ".join(dipwhy),
        "CakilmaRiski": risk,
        "KorumaKarari": protect,
        "RiskNeden": "; ".join(riskwhy),
        "GecmisPuan": history_score,
        "GecmisDurum": history_grade,
        "TeknikNeden": "; ".join(why),
    }

class RootView(BoxLayout):
    status = StringProperty("Hazır • Önce BAĞLANTI TESTİ'ne bas.")
    result_text = StringProperty(
        "[b]v2.3 TradingView veri motoru[/b]\\n\\n"
        "Yahoo kaldırıldı. Bu sürüm BIST sembollerini TradingView tarama uç noktasından "
        "toplu olarak alır. Böylece yüzlerce ayrı fiyat isteği göndermez.\\n\\n"
        "Önce BAĞLANTI TESTİ'ne bas."
    )
    scanning = BooleanProperty(False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.cancelled = False
        self.data = {"top":[], "dip":[], "history":[], "risk":[]}

    def _set_status(self, txt):
        Clock.schedule_once(lambda dt: setattr(self, "status", txt), 0)

    def test_connection(self):
        if self.scanning:
            return
        self.scanning = True
        threading.Thread(target=self._test_worker, daemon=True).start()

    def _test_worker(self):
        try:
            rows = tv_scan_symbols(["THYAO"])
            if not rows:
                raise RuntimeError("THYAO sonucu boş")
            x = row_to_dict(rows[0])
            msg = (
                "[b]BAĞLANTI BAŞARILI[/b]\\n\\n"
                f"{x['symbol']} • Fiyat: {fnum(x['close']):.2f}\\n"
                f"RSI: {fnum(x['RSI'], 50):.1f}\\n"
                f"3A performans: %{fnum(x['Perf.3M']):.2f}\\n\\n"
                "Şimdi PİYASAYI TARA düğmesine basabilirsin."
            )
            Clock.schedule_once(lambda dt: setattr(self, "result_text", msg), 0)
            self._set_status("Bağlantı başarılı • TradingView veri alındı.")
        except Exception as e:
            err = str(e)
            Clock.schedule_once(lambda dt: setattr(
                self, "result_text",
                "[b]BAĞLANTI HATASI[/b]\\n\\n" + err
            ), 0)
            self._set_status("Bağlantı başarısız: " + err)
        finally:
            Clock.schedule_once(lambda dt: setattr(self, "scanning", False), 0)

    def start_scan(self):
        if self.scanning:
            return
        self.scanning = True
        self.cancelled = False
        self.result_text = "Tarama hazırlanıyor..."
        threading.Thread(target=self._scan_worker, daemon=True).start()

    def cancel_scan(self):
        self.cancelled = True
        self._set_status("İptal isteniyor...")

    def _scan_worker(self):
        try:
            tickers = load_tickers()
            total = len(tickers)
            results = []
            errors = []
            batch_size = 120

            for start in range(0, total, batch_size):
                if self.cancelled:
                    self._set_status("Tarama iptal edildi.")
                    return
                batch = tickers[start:start+batch_size]
                self._set_status(f"Tarama: {start}/{total} • Toplu veri alınıyor...")
                try:
                    rows = tv_scan_symbols(batch)
                    for row in rows:
                        try:
                            results.append(score_row(row_to_dict(row)))
                        except Exception as e:
                            if len(errors) < 10:
                                errors.append(str(e))
                except Exception as e:
                    if len(errors) < 10:
                        errors.append(f"Batch {start}: {e}")
                time.sleep(0.8)

            self.data["top"] = sorted(results, key=lambda x: (x["GenelPuan"], x["TeknikPuan"]), reverse=True)[:30]
            self.data["dip"] = sorted([x for x in results if x["DipPuan"] >= 45], key=lambda x: x["DipPuan"], reverse=True)[:30]
            self.data["history"] = sorted(results, key=lambda x: x["GecmisPuan"], reverse=True)[:30]
            self.data["risk"] = sorted(results, key=lambda x: x["CakilmaRiski"], reverse=True)[:30]

            if results:
                self._set_status(f"Tamamlandı • {len(results)}/{total} sembol")
                Clock.schedule_once(lambda dt: self.show_group("top"), 0)
            else:
                detail = "\\n".join(errors[:5]) if errors else "Veri dönmedi."
                Clock.schedule_once(lambda dt: setattr(
                    self, "result_text",
                    "[b]TARAMA BAŞARISIZ[/b]\\n\\n" + detail
                ), 0)
                self._set_status("Tarama veri alamadı.")
        except Exception as e:
            self._set_status("Hata: " + str(e))
        finally:
            Clock.schedule_once(lambda dt: setattr(self, "scanning", False), 0)

    def show_group(self, key):
        titles = {
            "top": "EN GÜÇLÜ ADAYLAR",
            "dip": "DİPTEN DÖNÜŞ ADAYLARI",
            "history": "GEÇMİŞ PERFORMANS",
            "risk": "RİSK RADARI",
        }
        items = self.data.get(key, [])
        lines = [f"[b]{titles.get(key, key)}[/b]\\n"]
        if not items:
            lines.append("Henüz sonuç yok.")
        for i, r in enumerate(items, 1):
            if key == "top":
                extra = f"Teknik {r['TeknikPuan']} • Risk {r['CakilmaRiski']} • RSI {r['RSI']} • 3A %{r['3Ay%']}"
            elif key == "dip":
                extra = f"Dip {r['DipPuan']} • Dipten %{r['DiptenUzaklik%']} • Teyit {r['DipTeyitSayisi']}"
            elif key == "history":
                extra = f"Geçmiş {r['GecmisPuan']} • 1A %{r['1Ay%']} • 3A %{r['3Ay%']} • 6A %{r['6Ay%']} • 1Y %{r['1Yil%']}"
            else:
                extra = f"Risk {r['CakilmaRiski']} • ATR %{r['ATR%']} • RSI {r['RSI']} • {r['KorumaKarari']}"
            lines.append(
                f"[b]{i}. {r['Varlik']}[/b] — Genel {r['GenelPuan']}\\n"
                f"{extra}\\n"
                f"{r['NihaiKarar']} • {r['Evre']}\\n"
            )
        self.result_text = "\\n".join(lines)

class QuantScannerApp(App):
    def build(self):
        self.title = "Quant Scanner Mobile v2.3"
        Builder.load_string(KV)
        return RootView()

QuantScannerApp().run()
