# XAUUSD Signal Bot

RSI + hacim + ATR tabanli, basit ve seffaf bir sinyal uretici. Her saat
GitHub Actions ile calisir, `signals_log.csv` dosyasina sinyal ekler ve
Actions calisma ozetinde (Summary) sonucu gosterir.

**Bu bir yatirim tavsiyesi degildir.** Egitim/arastirma amaclidir. Gercek
parayla islem yapmadan once mutlaka kendi testinizi (backtest) yapin.

## Nasil calisir

- Veri kaynagi: [yfinance](https://pypi.org/project/yfinance/) ile `GC=F`
  (altin futures). XAUUSD spot fiyatina cok yakin hareket eder ama birebir
  ayni degildir; forex/CFD piyasalarinda "gercek" hacim olmadigi icin burada
  kullanilan hacim, futures islem hacmidir (tick volume degil, gercek islem
  hacmi — ama yine de spot XAUUSD hacminden farklidir).
- Indikatorler: RSI(14), EMA(50) trend filtresi, 20 periyotluk hacim
  ortalamasi, ATR(14).
- Sinyal mantigi:
  - **BUY**: RSI asagidan yukari 30 seviyesini kesiyor, fiyat EMA50'nin
    ustunde ve hacim 20 periyot ortalamasinin en az 1.2 katinda.
  - **SELL**: RSI yukaridan asagi 70 seviyesini kesiyor, fiyat EMA50'nin
    altinda ve hacim teyitli.
  - Aksi halde **HOLD** (islem yok).
- SL/TP: ATR bazli. SL = giris ∓ 1.5×ATR, TP = giris ± 3×ATR (yaklasik
  1:2 risk/odul).

Tum esikler (`RSI_OVERSOLD`, `VOLUME_CONFIRM_MULT`, `ATR_SL_MULT`,
`ATR_TP_MULT`, `INTERVAL`, ...) `xauusd_signal.py` dosyasinin ustunde,
tek yerden ayarlanabilir.

## Kurulum

1. Bu klasoru bir GitHub reposuna push edin.
2. Repo Settings → Actions → General → Workflow permissions altinda
   "Read and write permissions" secili oldugundan emin olun (log dosyasinin
   otomatik commit'lenebilmesi icin).
3. Actions sekmesinden workflow'u manuel tetikleyip (`workflow_dispatch`)
   test edebilirsiniz; sonrasinda cron her saat calisir.

## Yerel calistirma

```bash
pip install -r requirements.txt
python xauusd_signal.py
```

## Sinirlamalar / bilinmesi gerekenler

- RSI + hacim tek basina guclu bir strateji degildir; yatay/sikismis
  piyasalarda yanlis sinyal (whipsaw) uretebilir.
- `GC=F` verisi, brokerlarin sundugu XAUUSD spot fiyatindan (spread, swap,
  seans farklari nedeniyle) hafifce sapabilir.
- Script gecmis veriye bakip an itibariyle bir sinyal uretir; otomatik
  emir gonderme/execution yapmaz. Bir brokera (orn. MT5, ccxt benzeri bir
  API) baglamak istersen ayri bir adim gerekir.
