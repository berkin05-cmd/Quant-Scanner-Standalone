QUANT SCANNER MOBILE v2.3 - TRADINGVIEW DATA MOTORU

Neden?
Yahoo Android tarafinda HTTP 429 verdi. Bu sürüm Yahoo'yu tamamen kaldırır.

Yeni veri yapısı:
- TradingView Turkey screener endpoint'i kullanılır.
- 714 sembol korunur.
- Semboller 120'lik gruplar halinde toplu sorgulanır.
- Tek tek 714 HTTP isteği gönderilmez.
- Bağlantı testi THYAO ile yapılır.

Korunan ekranlar:
- En Güçlü
- Dip
- Risk

Önemli değişiklik:
- Eski "Backtest" butonu "Geçmiş" olarak değiştirildi.
- Bunun nedeni bu veri kaynağının bu sürümde tam günlük OHLC geçmişi sağlamamasıdır.
- "Geçmiş" sekmesi 1A/3A/6A/1Y performanslarını gösterir; bu gerçek sinyal backtest'i değildir.

Not:
TradingView screener endpoint'i resmi kamu API'si değildir; ileride değişebilir.
