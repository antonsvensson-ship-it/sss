"""
Ombalanseringsbot för OKX (EU).

Regel: håll ungefär MAL_ANDEL i krypto och resten i euro.
  - Har priset stigit så att kryptoandelen ligger över MAL_ANDEL + BAND  -> sälj tillbaka till målet.
  - Har priset fallit så att kryptoandelen ligger under MAL_ANDEL - BAND -> köp tillbaka till målet.
  - Annars: gör ingenting.
Boten köper alltså efter fall och säljer efter uppgångar, men gissar aldrig framtida priser.

Inställningar (miljövariabler):
  PAR        handelspar, standard BTC-EUR
  BUDGET     max euro boten får använda, standard 90 (ca 1 000 kr)
  MAL_ANDEL  mål för kryptoandel, standard 0.5 (50 %)
  BAND       tillåten avvikelse innan boten agerar, standard 0.10 (10 procentenheter)
  LIVE       "1" för riktiga affärer, annars testläge
  OKX_DEMO   "1" för OKX:s demokonto
"""
import os, sys
from bot import anrop, LIVE, DEMO

PAR = (os.environ.get("PAR") or "BTC-EUR").upper()
BUDGET = float((os.environ.get("BUDGET") or "90"))
MAL_ANDEL = float((os.environ.get("MAL_ANDEL") or "0.5"))
BAND = float((os.environ.get("BAND") or "0.10"))
MIN_AFFAR = 5.0                  # under så här många euro lönar sig inte avgiften
MAX_AFFAR = BUDGET * 0.4         # spärr: aldrig mer än 40 % av budgeten i en affär

KRYPTO, VALUTA = PAR.split("-")


def pris():
    return float(anrop("GET", f"/api/v5/market/ticker?instId={PAR}")[0]["last"])


def saldon():
    data = anrop("GET", f"/api/v5/account/balance?ccy={KRYPTO},{VALUTA}")
    s = {d["ccy"]: float(d["availBal"]) for d in data[0].get("details", [])}
    return s.get(KRYPTO, 0.0), s.get(VALUTA, 0.0)


def berakna(krypto_mangd, euro, kurs):
    """Returnerar ('köp'|'sälj'|None, belopp i euro, kryptoandel)."""
    euro_i_spel = min(euro, BUDGET)  # boten rör bara budgeten, inte resten av kontot
    krypto_varde = krypto_mangd * kurs
    totalt = krypto_varde + euro_i_spel
    if totalt < MIN_AFFAR:
        return None, 0.0, 0.0
    andel = krypto_varde / totalt
    if abs(andel - MAL_ANDEL) <= BAND:
        return None, 0.0, andel
    belopp = min(abs(totalt * MAL_ANDEL - krypto_varde), MAX_AFFAR)
    if belopp < MIN_AFFAR:
        return None, 0.0, andel
    return ("köp" if andel < MAL_ANDEL else "sälj"), belopp, andel


def main():
    if not 0 < MAL_ANDEL < 1 or not 0 < BAND < 0.5:
        sys.exit("Ogiltig MAL_ANDEL eller BAND.")
    kurs = pris()
    krypto_mangd, euro = saldon()
    atgard, belopp, andel = berakna(krypto_mangd, euro, kurs)
    lage = "RIKTIGT" if LIVE else "TESTLÄGE"
    print(f"[{lage}{' demo' if DEMO else ''}] {PAR} {kurs:.2f} | {krypto_mangd:.8f} {KRYPTO}, "
          f"{euro:.2f} {VALUTA} | kryptoandel {andel:.1%} (mål {MAL_ANDEL:.0%} ± {BAND:.0%})")

    if atgard is None:
        print("Inom gränserna, ingen affär.")
        return
    print(f"Åtgärd: {atgard} för {belopp:.2f} {VALUTA}")
    if not LIVE:
        print("Testläge: ingen order skickad. Sätt LIVE=1 för riktiga affärer.")
        return

    if atgard == "köp":
        order = {"instId": PAR, "tdMode": "cash", "side": "buy", "ordType": "market",
                 "sz": f"{belopp:.2f}", "tgtCcy": "quote_ccy"}
    else:
        mangd = min(belopp / kurs, krypto_mangd)
        order = {"instId": PAR, "tdMode": "cash", "side": "sell", "ordType": "market",
                 "sz": f"{mangd:.8f}", "tgtCcy": "base_ccy"}
    svar = anrop("POST", "/api/v5/trade/order", order)
    print(f"Order lagd, id {svar[0]['ordId']}")


if __name__ == "__main__":
    main()
