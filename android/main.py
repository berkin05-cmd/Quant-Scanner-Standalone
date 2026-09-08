
import os, json, math, time, threading, ssl
import requests, certifi
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from kivy.app import App
from kivy.clock import Clock
from kivy.lang import Builder
from kivy.properties import StringProperty, BooleanProperty
from kivy.uix.boxlayout import BoxLayout

APP_DIR = os.path.dirname(os.path.abspath(__file__))
TICKER_FILE = os.path.join(APP_DIR, "tickers_bist.txt")

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
        text: "Bağımsız Android sürümü • Bilgisayar/sunucu gerekmez"
        size_hint_y: None
        height: dp(26)
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
        height: dp(48)
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
            text: "Backtest"
            on_release: root.show_group("backtest")
        Button:
            text: "Risk"
            on_release: root.show_group("risk")

    ScrollView:
        do_scroll_x: False
        Label:
            id: results
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

def sma(vals, n, i=None):
    if i is None:
        i = len(vals) - 1
    if i + 1 < n:
        return None
    a = vals[i-n+1:i+1]
    if len(a) < n:
        return None
    return sum(a) / n

def ema_series(vals, span):
    if not vals:
        return []
    a = 2.0 / (span + 1.0)
    out = [float(vals[0])]
    for x in vals[1:]:
        out.append(a * float(x) + (1-a) * out[-1])
    return out

def rsi_series(vals, n=14):
    if len(vals) < 2:
        return [50.0] * len(vals)
    gains = [0.0]
    losses = [0.0]
    for i in range(1, len(vals)):
        d = vals[i] - vals[i-1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    alpha = 1.0 / n
    ag = gains[0]
    al = losses[0]
    out = [50.0]
    for i in range(1, len(vals)):
        ag = alpha*gains[i] + (1-alpha)*ag
        al = alpha*losses[i] + (1-alpha)*al
        if al <= 1e-12:
            out.append(100.0 if ag > 0 else 50.0)
        else:
            rs = ag/al
            out.append(100.0 - 100.0/(1.0+rs))
    return out

def atr_series(h, l, c, n=14):
    tr = []
    for i in range(len(c)):
        if i == 0:
            tr.append(abs(h[i]-l[i]))
        else:
            tr.append(max(abs(h[i]-l[i]), abs(h[i]-c[i-1]), abs(l[i]-c[i-1])))
    out = [None] * len(c)
    s = 0.0
    for i, x in enumerate(tr):
        s += x
        if i >= n:
            s -= tr[i-n]
        if i >= n-1:
            out[i] = s/n
    return out

def pct(c, n):
    if len(c) <= n or c[-1-n] == 0:
        return 0.0
    return (c[-1]/c[-1-n]-1.0)*100.0

def rolling_min(a, n):
    return min(a[-n:]) if len(a) >= n else min(a)

def rolling_max(a, n):
    return max(a[-n:]) if len(a) >= n else max(a)

def yahoo_chart(ticker, range_="2y"):
    """
    Android için doğrudan Yahoo Chart endpoint'ine bağlanır.
    certifi CA paketi kullanır; iki Yahoo hostu arasında fallback yapar.
    """
    urls = [
        f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range={range_}&interval=1d&events=history&includeAdjustedClose=false",
        f"https://query2.finance.yahoo.com/v8/finance/chart/{ticker}?range={range_}&interval=1d&events=history&includeAdjustedClose=false",
    ]
    headers = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36",
        "Accept": "application/json,text/plain,*/*",
        "Connection": "close",
    }
    last = None
    for url in urls:
        try:
            r = requests.get(url, headers=headers, timeout=15, verify=certifi.where())
            if r.status_code == 429:
                raise RuntimeError("HTTP 429 - veri sağlayıcı hız sınırı")
            if r.status_code >= 400:
                raise RuntimeError(f"HTTP {r.status_code}")
            data = r.json()
            result = (data.get("chart") or {}).get("result")
            if not result:
                err = (data.get("chart") or {}).get("error")
                raise RuntimeError(f"Yahoo boş sonuç: {err}")
            x = result[0]
            q = ((x.get("indicators") or {}).get("quote") or [{}])[0]
            ts = x.get("timestamp") or []
            oo = q.get("open") or []
            hh = q.get("high") or []
            ll = q.get("low") or []
            cc = q.get("close") or []
            vv = q.get("volume") or []
            rows = []
            for i in range(min(len(ts), len(cc))):
                if cc[i] is None or hh[i] is None or ll[i] is None:
                    continue
                rows.append((
                    int(ts[i]),
                    fnum(oo[i] if i < len(oo) else cc[i], fnum(cc[i])),
                    fnum(hh[i]),
                    fnum(ll[i]),
                    fnum(cc[i]),
                    fnum(vv[i] if i < len(vv) else 0.0),
                ))
            if len(rows) < 220:
                raise RuntimeError(f"Yetersiz veri: {len(rows)} bar")
            return rows
        except Exception as e:
            last = e
    raise last or RuntimeError("Veri alınamadı")

def calc_indicators(rows):
    c = [x[4] for x in rows]
    h = [x[2] for x in rows]
    l = [x[3] for x in rows]
    v = [x[5] for x in rows]
    n = len(c)
    if n < 220:
        return None

    e12 = ema_series(c, 12)
    e26 = ema_series(c, 26)
    macd = [e12[i]-e26[i] for i in range(n)]
    macds = ema_series(macd, 9)
    rsi = rsi_series(c, 14)
    atr = atr_series(h, l, c, 14)

    p = c[-1]
    ma20 = sma(c, 20)
    ma50 = sma(c, 50)
    ma200 = sma(c, 200)
    lo20 = rolling_min(l, 20)
    lo252 = rolling_min(l, min(252, n))
    hi55 = rolling_max(h, 55)
    hi252 = rolling_max(h, min(252, n))
    vol20 = sum(v[-20:])/20.0 if len(v) >= 20 else 0.0
    volr = (v[-1]/vol20) if vol20 > 0 else 1.0
    atrv = atr[-1] or 0.0
    atrp = atrv/p*100.0 if p else 0.0
    dd = (p/hi252-1.0)*100.0 if hi252 else 0.0

    return {
        "close": p, "ma20": ma20, "ma50": ma50, "ma200": ma200,
        "rsi": rsi[-1], "macd": macd[-1], "macds": macds[-1],
        "atr": atrv, "atrp": atrp, "volr": volr,
        "lo20": lo20, "lo252": lo252, "hi55": hi55, "hi252": hi252,
        "r1m": pct(c, 21), "r3m": pct(c, 63), "r5m": pct(c, 105),
        "r12m": pct(c, min(252, n-1)), "dd252": dd,
        "_c": c, "_h": h, "_l": l, "_v": v, "_rsi": rsi, "_macd": macd, "_macds": macds,
        "_atr": atr,
    }

def technical_score(ind, bench_r3=None):
    p = ind["close"]
    m20, m50, m200 = ind["ma20"], ind["ma50"], ind["ma200"]
    rsi, macd, macds = ind["rsi"], ind["macd"], ind["macds"]
    r1, r3, r5, r12 = ind["r1m"], ind["r3m"], ind["r5m"], ind["r12m"]
    vr, atrp = ind["volr"], ind["atrp"]
    hi, lo, dd = ind["hi55"], ind["lo20"], ind["dd252"]
    s = 0
    why = []

    def add(cond, pts, txt):
        nonlocal s
        if cond:
            s += pts
            why.append(txt)

    add(m20 is not None and p > m20, 8, "MA20 üstü")
    add(m50 is not None and p > m50, 10, "MA50 üstü")
    add(m200 is not None and p > m200, 12, "MA200 üstü")
    add(m20 is not None and m50 is not None and m20 > m50, 8, "20>50")
    add(m50 is not None and m200 is not None and m50 > m200, 10, "50>200")
    add(macd > macds, 8, "MACD+")
    add(50 <= rsi <= 68, 8, "RSI dengeli")
    add(r1 > 0, 4, "1A+")
    add(r3 > 0, 5, "3A+")
    add(r5 > 0, 4, "5A+")
    add(vr >= 1.2, 6, "Hacim+")
    add(p >= hi*.995 and vr >= 1.15, 8, "55G kırılım")

    rel = None
    if bench_r3 is not None:
        rel = r3 - bench_r3
        if rel > 5:
            s += 7; why.append("Relatif güç+")
        elif rel < 0:
            s -= 5

    if m20 and (p/m20-1)*100 > 15: s -= 10
    if rsi > 75: s -= 10
    if atrp > 6: s -= 5
    if dd < -30: s -= 4
    s = max(0, min(100, int(round(s))))

    if rsi >= 76 or (m20 and (p/m20-1)*100 > 15):
        phase = "AŞIRI ISINMIŞ"
    elif p >= hi*.995 and vr >= 1.15:
        phase = "KIRILIM"
    elif m20 and m50 and m200 and p > m50 and p > m200 and m20 > m50 and rsi >= 50:
        phase = "GÜÇLÜ TREND"
    elif m20 and m50 and m200 and p > m200 and m20 > m50 and 45 <= rsi <= 62:
        phase = "ERKEN / DÖNÜŞ"
    elif m200 and p < m200:
        phase = "ZAYIF TREND"
    else:
        phase = "KARMA"

    atrv = ind["atr"]
    stop = max(lo, p-2*atrv) if atrv > 0 else lo
    risk = max(p-stop, 0.0001)
    target = max(hi, p+3*atrv) if atrv > 0 else hi
    rr = max(0.0, (target-p)/risk)

    return {
        "TeknikPuan": s, "Evre": phase, "Fiyat": round(p, 2),
        "RSI": round(rsi, 1), "ATR%": round(atrp, 2),
        "1Ay%": round(r1, 2), "3Ay%": round(r3, 2), "5Ay%": round(r5, 2), "12Ay%": round(r12, 2),
        "Relatif3Ay%": round(rel, 2) if rel is not None else "",
        "Destek": round(lo, 2), "Direnc": round(hi, 2),
        "ATR_Stop": round(stop, 2), "ATR_Hedef": round(target, 2),
        "RiskOdul": round(rr, 2), "52H_Zirve_Uzaklik%": round(dd, 2),
        "TeknikNeden": "; ".join(why)
    }

def dip_score(ind, tech):
    p = ind["close"]
    lo252 = ind["lo252"]
    near = ((p/lo252)-1)*100 if lo252 else 999
    score = 0
    conf = 0
    why = []
    if near <= 6: score += 35; why.append("52H dibe çok yakın")
    elif near <= 12: score += 25; why.append("52H dibe yakın")
    elif near <= 20: score += 12

    rsi = ind["rsi"]
    if 35 <= rsi <= 55: score += 15; conf += 1; why.append("RSI toparlanma bölgesi")
    if ind["macd"] > ind["macds"]: score += 15; conf += 1; why.append("MACD pozitif")
    if ind["ma20"] and p > ind["ma20"]: score += 15; conf += 1; why.append("MA20 üstü")
    if ind["volr"] >= 1.2: score += 10; conf += 1; why.append("Hacim teyidi")
    if ind["r1m"] > 0: score += 10; conf += 1; why.append("1A pozitif")

    if tech["Evre"] == "ZAYIF TREND": score -= 15
    if ind["r3m"] < -20: score -= 10
    if ind["atrp"] > 7: score -= 10

    score = max(0, min(100, int(score)))
    if score >= 70 and conf >= 3:
        durum = "DÖNÜŞ ADAYI"
    elif score >= 50:
        durum = "BEKLE / TEYİT"
    else:
        durum = "ZAYIF"
    return score, durum, near, conf, "; ".join(why)

def backtest(rows):
    c = [x[4] for x in rows]
    h = [x[2] for x in rows]
    l = [x[3] for x in rows]
    n = len(c)
    if n < 230:
        return {"n":0,"win3":0,"avg3":0,"mae3":0,"grade":"YETERSİZ"}

    e12 = ema_series(c,12)
    e26 = ema_series(c,26)
    macd = [e12[i]-e26[i] for i in range(n)]
    macds = ema_series(macd,9)
    rsi = rsi_series(c,14)
    signals = []
    last_sig = -99

    start = max(200, n-320)
    for i in range(start, n-6):
        m20 = sma(c,20,i)
        if m20 is None: continue
        sig = c[i] > m20 and 45 <= rsi[i] <= 72 and macd[i] > macds[i]
        if sig and i-last_sig >= 3:
            signals.append(i); last_sig = i

    if not signals:
        return {"n":0,"win3":0,"avg3":0,"mae3":0,"grade":"YETERSİZ"}

    rets = []
    maes = []
    for i in signals:
        entry = c[i]
        r3 = (c[i+3]/entry-1)*100
        mae3 = (min(l[i+1:i+4])/entry-1)*100
        rets.append(r3); maes.append(mae3)

    nn = len(rets)
    win = sum(1 for x in rets if x > 0)/nn*100
    avg = sum(rets)/nn
    mae = sum(maes)/nn
    if nn >= 30 and win >= 60 and avg > 0 and mae > -4:
        grade = "GÜÇLÜ"
    elif nn >= 15 and win >= 55 and avg > 0 and mae > -6:
        grade = "ORTA"
    elif nn < 8:
        grade = "YETERSİZ"
    else:
        grade = "ZAYIF"
    return {"n":nn,"win3":win,"avg3":avg,"mae3":mae,"grade":grade}

def protection(tech, ind, bt):
    risk = 0
    reasons = []
    atrp = ind["atrp"]
    rsi = ind["rsi"]
    rr = tech["RiskOdul"]
    if atrp >= 8: risk += 30; reasons.append("ATR çok yüksek")
    elif atrp >= 6: risk += 18
    if rsi >= 82: risk += 25; reasons.append("RSI aşırı")
    elif rsi >= 75: risk += 12
    if tech["Evre"] == "AŞIRI ISINMIŞ": risk += 20
    if ind["r1m"] < -10: risk += 15
    if ind["r3m"] < -20: risk += 15
    if rr < 0.8: risk += 20; reasons.append("R/R zayıf")
    if bt["grade"] == "ZAYIF" and bt["n"] >= 15: risk += 15; reasons.append("Backtest zayıf")
    risk = max(0, min(100, int(risk)))
    karar = "ALMA" if risk >= 65 else "BEKLE" if risk >= 40 else "ADAY"
    return risk, karar, "; ".join(reasons)

def load_tickers():
    try:
        with open(TICKER_FILE, "r", encoding="utf-8") as f:
            out = []
            for line in f:
                s = line.strip().upper().replace(".IS","")
                if s and not s.startswith("#"):
                    out.append(s)
            return list(dict.fromkeys(out))
    except Exception:
        return ["AKBNK","ASELS","BIMAS","EREGL","GARAN","ISCTR","KCHOL","SAHOL","THYAO","TUPRS"]

class RootView(BoxLayout):
    status = StringProperty("Hazır • İnternet bağlantısı gerekli.")
    result_text = StringProperty(
        "[b]Bağımsız sürüm[/b]\n\n"
        "Bu APK bilgisayara veya yerel sunucuya bağlanmaz.\n"
        "Veriyi doğrudan internetten alır ve analizi telefonun içinde yapar.\n\n"
        "PİYASAYI TARA düğmesine dokun."
    )
    scanning = BooleanProperty(False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.cancelled = False
        self.data = {"top":[],"dip":[],"backtest":[],"risk":[]}
        self.all_rows = []

    def test_connection(self):
        if self.scanning:
            return
        self.status = "Bağlantı test ediliyor..."
        self.result_text = "THYAO.IS için Yahoo bağlantısı test ediliyor..."
        threading.Thread(target=self._test_connection_worker, daemon=True).start()

    def _test_connection_worker(self):
        try:
            rows = yahoo_chart("THYAO.IS", "1y")
            ind = calc_indicators(rows)
            msg = (
                "[b]BAĞLANTI BAŞARILI[/b]\n\n"
                f"THYAO.IS • {len(rows)} günlük veri\n"
                f"Son fiyat: {ind['close']:.2f}\n"
                f"RSI: {ind['rsi']:.1f}\n\n"
                "Artık PİYASAYI TARA düğmesine basabilirsin."
            )
            Clock.schedule_once(lambda dt: setattr(self, "result_text", msg), 0)
            self._set_status("Bağlantı başarılı • Veri alınıyor.")
        except Exception as e:
            err = str(e)
            msg = (
                "[b]BAĞLANTI HATASI[/b]\n\n"
                + err +
                "\n\nBu mesaj gerçek hata nedenidir."
            )
            Clock.schedule_once(lambda dt: setattr(self, "result_text", msg), 0)
            self._set_status("Bağlantı başarısız: " + err)

    def start_scan(self):
        if self.scanning:
            return
        self.scanning = True
        self.cancelled = False
        self.data = {"top":[],"dip":[],"backtest":[],"risk":[]}
        self.all_rows = []
        self.result_text = "Tarama hazırlanıyor..."
        threading.Thread(target=self._scan_worker, daemon=True).start()

    def cancel_scan(self):
        self.cancelled = True
        self.status = "İptal isteniyor..."

    def _set_status(self, txt):
        Clock.schedule_once(lambda dt: setattr(self, "status", txt), 0)

    def _finish(self, txt=None):
        def done(dt):
            self.scanning = False
            if txt:
                self.status = txt
            self.show_group("top")
        Clock.schedule_once(done, 0)

    def _scan_worker(self):
        try:
            tickers = load_tickers()
            total = len(tickers)
            self._set_status(f"BIST listesi: {total} sembol • Endeks verisi alınıyor...")

            bench_r3 = None
            try:
                b = calc_indicators(yahoo_chart("XU100.IS", "1y"))
                if b: bench_r3 = b["r3m"]
            except Exception:
                pass

            results = []
            errors = 0
            done = 0
            first_errors = []

            def work(sym):
                rows = yahoo_chart(sym + ".IS", "2y")
                ind = calc_indicators(rows)
                if not ind:
                    raise ValueError("Gösterge hesaplanamadı")
                tech = technical_score(ind, bench_r3)
                dip, dipdur, near, conf, dipwhy = dip_score(ind, tech)
                bt = backtest(rows)
                risk, protect, riskwhy = protection(tech, ind, bt)
                overall = max(0, min(100, int(round(tech["TeknikPuan"]*0.78 + dip*0.12 + (70 if bt["grade"]=="GÜÇLÜ" else 55 if bt["grade"]=="ORTA" else 45)*0.10))))
                if protect == "ALMA":
                    final = "UZAK DUR / YÜKSEK RİSK"
                elif overall >= 72 and tech["TeknikPuan"] >= 65:
                    final = "GÜÇLÜ ADAY"
                elif overall >= 60:
                    final = "İZLE"
                else:
                    final = "KARMA / BEKLE"
                return {
                    "Varlik": sym, "GenelPuan": overall, "NihaiKarar": final,
                    "DipPuan": dip, "DipDurum": dipdur, "DiptenUzaklik%": round(near,2),
                    "DipTeyitSayisi": conf, "DipNeden": dipwhy,
                    "CakilmaRiski": risk, "KorumaKarari": protect, "RiskNeden": riskwhy,
                    "BT_SinyalSayisi": bt["n"], "BT_3G_Kazanma%": round(bt["win3"],1),
                    "BT_3G_OrtGetiri%": round(bt["avg3"],2), "BT_3G_OrtMAE%": round(bt["mae3"],2),
                    "BT_Guven": bt["grade"], **tech
                }

            # Moderate parallelism to avoid overloading phone/network
            with ThreadPoolExecutor(max_workers=2) as ex:
                futs = {ex.submit(work, s): s for s in tickers}
                for fut in as_completed(futs):
                    done += 1
                    if self.cancelled:
                        for f in futs: f.cancel()
                        break
                    try:
                        results.append(fut.result())
                    except Exception as e:
                        errors += 1
                        if len(first_errors) < 5:
                            first_errors.append(f"{futs[fut]}: {e}")
                    if done % 5 == 0 or done == total:
                        self._set_status(f"Tarama: {done}/{total} • Başarılı {len(results)} • Veri hatası {errors}")
                    time.sleep(0.18)

            if self.cancelled:
                self._finish("Tarama iptal edildi.")
                return

            self.all_rows = results
            self.data["top"] = sorted(results, key=lambda x: (x["GenelPuan"], x["TeknikPuan"]), reverse=True)[:30]
            self.data["dip"] = sorted([x for x in results if x["DipPuan"] >= 45], key=lambda x: x["DipPuan"], reverse=True)[:30]
            self.data["backtest"] = sorted([x for x in results if x["BT_SinyalSayisi"] >= 8], key=lambda x: (x["BT_3G_Kazanma%"], x["BT_3G_OrtGetiri%"]), reverse=True)[:30]
            self.data["risk"] = sorted(results, key=lambda x: x["CakilmaRiski"], reverse=True)[:30]

            if results:
                self._finish(f"Tamamlandı • {len(results)}/{total} sembol • {errors} veri hatası")
            else:
                detail = "\n".join(first_errors) if first_errors else "Bilinmeyen veri hatası"
                Clock.schedule_once(lambda dt: setattr(self, "result_text",
                    "[b]TARAMA VERİ ALAMADI[/b]\n\nİlk hatalar:\n" + detail), 0)
                self._finish("Tarama başarısız • Gerçek hata aşağıda gösterildi")
        except Exception as e:
            self._finish("Hata: " + str(e))

    def show_group(self, key):
        title = {
            "top":"EN GÜÇLÜ ADAYLAR",
            "dip":"DİPTEN DÖNÜŞ ADAYLARI",
            "backtest":"BACKTEST LİDERLERİ",
            "risk":"RİSK RADARI"
        }.get(key, key)

        items = self.data.get(key, [])
        lines = [f"[b]{title}[/b]\n"]
        if not items:
            lines.append("Henüz sonuç yok. Önce piyasayı tara.")
        for i, r in enumerate(items, 1):
            if key == "top":
                extra = f"Teknik {r['TeknikPuan']} • Risk {r['CakilmaRiski']} • RSI {r['RSI']} • 3A %{r['3Ay%']}"
            elif key == "dip":
                extra = f"Dip {r['DipPuan']} • Dipten %{r['DiptenUzaklik%']} • Teyit {r['DipTeyitSayisi']} • Risk {r['CakilmaRiski']}"
            elif key == "backtest":
                extra = f"3G kazanma %{r['BT_3G_Kazanma%']} • Ort %{r['BT_3G_OrtGetiri%']} • N={r['BT_SinyalSayisi']} • {r['BT_Guven']}"
            else:
                extra = f"Risk {r['CakilmaRiski']} • ATR %{r['ATR%']} • RSI {r['RSI']} • {r['KorumaKarari']}"
            lines.append(
                f"[b]{i}. {r['Varlik']}[/b] — Genel {r['GenelPuan']}\n"
                f"{extra}\n"
                f"{r['NihaiKarar']} • {r['Evre']}\n"
            )
        self.result_text = "\n".join(lines)

class QuantScannerApp(App):
    def build(self):
        self.title = "Quant Scanner Mobile Standalone"
        Builder.load_string(KV)
        return RootView()

QuantScannerApp().run()
