"""
Enkel köpbot för OKX (EU): köper ett fast belopp krypto varje gång den körs.
Ingen prisförutsägelse, ingen försäljning, ingen hävstång. Bara återkommande köp.

Inställningar via miljövariabler:
  OKX_API_KEY, OKX_API_SECRET, OKX_PASSPHRASE  (från OKX, bara "Trade"-behörighet, INTE "Withdraw")
  KOP                 t.ex. "BTC-EUR:60,ETH-EUR:30"  (par:belopp i EUR per körning)
  LIVE                "1" för riktiga köp. Allt annat = testläge (ingen order skickas).
  OKX_DEMO            "1" för OKX:s demokonto (låtsaspengar)
  OKX_BASE_URL        standard https://eea.okx.com (OKX:s EU-adress)
"""
import base64, datetime, hashlib, hmac, json, os, sys, urllib.request, urllib.error

BASE = (os.environ.get("OKX_BASE_URL") or "https://eea.okx.com").rstrip("/")
LIVE = os.environ.get("LIVE") == "1"
DEMO = os.environ.get("OKX_DEMO") == "1"
MAX_PER_KOP = 500  # spärr: vägrar köpa mer än så här många EUR per par och körning


def signera(tid, metod, sokvag, kropp, hemlighet):
    msg = f"{tid}{metod}{sokvag}{kropp}".encode()
    return base64.b64encode(hmac.new(hemlighet.encode(), msg, hashlib.sha256).digest()).decode()


def anrop(metod, sokvag, data=None):
    nyckel = os.environ["OKX_API_KEY"]
    hemlighet = os.environ["OKX_API_SECRET"]
    fras = os.environ["OKX_PASSPHRASE"]
    kropp = json.dumps(data) if data is not None else ""
    tid = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    rubriker = {
        "OK-ACCESS-KEY": nyckel,
        "OK-ACCESS-SIGN": signera(tid, metod, sokvag, kropp, hemlighet),
        "OK-ACCESS-TIMESTAMP": tid,
        "OK-ACCESS-PASSPHRASE": fras,
        "Content-Type": "application/json",
    }
    if DEMO:
        rubriker["x-simulated-trading"] = "1"
    req = urllib.request.Request(BASE + sokvag, data=kropp.encode() or None, headers=rubriker, method=metod)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            svar = json.load(r)
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP-fel {e.code}: {e.read().decode()[:300]}")
    if svar.get("code") != "0":
        sys.exit(f"OKX svarade med fel: {svar}")
    return svar["data"]


def las_kop():
    rad = (os.environ.get("KOP") or "BTC-EUR:50")
    kop = []
    for del_ in rad.split(","):
        par, belopp = del_.strip().split(":")
        belopp = float(belopp)
        if not 0 < belopp <= MAX_PER_KOP:
            sys.exit(f"Ogiltigt belopp för {par}: {belopp} (max {MAX_PER_KOP} EUR)")
        kop.append((par.strip().upper(), belopp))
    return kop


def eur_saldo():
    data = anrop("GET", "/api/v5/account/balance?ccy=EUR")
    detaljer = data[0].get("details", [])
    return float(detaljer[0]["availBal"]) if detaljer else 0.0


def main():
    kop = las_kop()
    totalt = sum(b for _, b in kop)
    lage = "RIKTIGA KÖP" if LIVE else "TESTLÄGE (inga köp görs)"
    print(f"{lage}{' på demokonto' if DEMO else ''}: {kop}, totalt {totalt:.2f} EUR")

    if not LIVE:
        print("Sätt LIVE=1 när du har testat och vill köpa på riktigt.")
        return

    saldo = eur_saldo()
    print(f"Tillgängligt: {saldo:.2f} EUR")
    if saldo < totalt:
        sys.exit(f"För lite pengar på kontot ({saldo:.2f} < {totalt:.2f} EUR). Inget köpt.")

    for par, belopp in kop:
        order = {
            "instId": par,
            "tdMode": "cash",          # vanlig spothandel, ingen hävstång
            "side": "buy",
            "ordType": "market",
            "sz": f"{belopp:.2f}",
            "tgtCcy": "quote_ccy",     # beloppet anges i EUR
        }
        svar = anrop("POST", "/api/v5/trade/order", order)
        print(f"Köpt {par} för {belopp:.2f} EUR, order-id {svar[0]['ordId']}")


if __name__ == "__main__":
    main()
