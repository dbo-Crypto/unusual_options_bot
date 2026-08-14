from datetime import date

from app.providers.occ import parse_occ_series_text, parse_occ_volume_csv


def test_parse_series_tabs():
    text = (
        "Series Search Results for AAPL\n"
        "AAPL  \t\t2026\t08\t14\t110\t000\tC P \t4\t113\t25000000\n"
        "AAPL  \t\t2026\t09\t18\t230\t000\tC P \t18835\t242\t25000000\n"
        "2AAPL\t\t2026\t08\t14\t280\t000\tP\t13\t0\t25000000\n"
    )
    rows = parse_occ_series_text(text, "AAPL", date(2026, 8, 13))
    assert len(rows) == 4
    first = [r for r in rows if r.strike == 110 and r.call_put == "C"][0]
    assert first.open_interest == 4
    put = [r for r in rows if r.strike == 110 and r.call_put == "P"][0]
    assert put.open_interest == 113
    assert all(not r.occ_symbol.startswith("2") for r in rows)


def test_parse_volume_csv():
    csv = (
        "quantity,underlying,symbol,actype,porc,exchange,actdate\n"
        "100,AAPL,AAPL,C,C,CBOE,08/12/2026,\n"
        "50,AAPL,AAPL,F,P,CBOE,08/12/2026,\n"
        "10,MSFT,MSFT,C,C,CBOE,08/12/2026,\n"
    )
    totals = parse_occ_volume_csv(csv, "AAPL")
    assert totals["C"] == 100
    assert totals["P"] == 50
