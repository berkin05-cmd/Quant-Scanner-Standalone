QUANT SCANNER MOBILE v2 — STANDALONE
====================================

Bu sürümde bilgisayar/backend sunucusu YOKTUR.

Telefon:
1) İnternetten günlük piyasa verisini doğrudan alır.
2) 714 sembollük BIST listesini APK içinden okur.
3) Teknik puan, dip dönüş, backtest özeti ve risk radarını telefonda hesaplar.
4) Yerel IP adresi veya 8000 portu istemez.

ÖNEMLİ:
- "Tek başına" bilgisayardan bağımsız demektir; güncel piyasa verisi için internet gerekir.
- Yahoo veri sağlayıcısı bazı sembollerde geçici veri hatası/rate-limit verebilir.
- 714 sembolün tam taraması telefonda ve bağlantıya göre uzun sürebilir.
- Bu bir yatırım garantisi değildir. Kaybetmeyi göze alamayacağınız para ile kısa vadeli işlem yapmak uygun değildir.

GITHUB'DA KULLANIM:
- Repodaki android klasörünü bu paketteki android klasörüyle değiştirin.
- .github/workflows/build-apk.yml dosyasını bu paketteki dosyayla değiştirin.
- Actions > Android APK Oluştur > Run workflow.
- Başarıdan sonra Artifacts bölümündeki Quant-Scanner-Mobile-STANDALONE-APK dosyasını indirin.
