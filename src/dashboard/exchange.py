"""Dollar exchange rate from the PTAX series of the Central Bank of Brazil."""

import json
import urllib.request
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

PTAX_URL = (
    "https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/"
    "CotacaoDolarPeriodo(dataInicial=@dataInicial,dataFinalCotacao=@dataFinalCotacao)"
    "?@dataInicial='{start}'&@dataFinalCotacao='{end}'"
    "&$top=100&$orderby=dataHoraCotacao%20desc&$format=json"
    "&$select=cotacaoVenda,dataHoraCotacao"
)
LOOKBACK_DAYS = 10
Opener = Callable[..., Any]


class ExchangeRateError(RuntimeError):
    """No dollar quote could be read from the Central Bank."""


def _bcb_date(day: date) -> str:
    """Format a day the way the PTAX API expects (MM-DD-YYYY).

    Parameters
    ----------
    day : date
        Day to format.

    Returns
    -------
    str
        Day as MM-DD-YYYY.
    """
    return day.strftime("%m-%d-%Y")


def latest_usd_sell_rate(today: date, opener: Opener = urllib.request.urlopen) -> tuple[float, str]:
    """Latest dollar selling rate published in the last days.

    Parameters
    ----------
    today : date
        Reference day; the search goes back ``LOOKBACK_DAYS`` days from it.
    opener : Callable[..., Any]
        Function that performs HTTP requests, replaceable in tests.

    Returns
    -------
    tuple[float, str]
        Selling rate in reais per dollar, and the date and time of the quote.

    Raises
    ------
    ExchangeRateError
        When the service cannot be reached or publishes no quote in the period.
    """
    url = PTAX_URL.format(
        start=_bcb_date(today - timedelta(days=LOOKBACK_DAYS)),
        end=_bcb_date(today),
    )
    try:
        request = urllib.request.Request(url, headers={"Accept": "application/json"})
        with opener(request, timeout=30) as response:
            payload = json.loads(response.read())
    except Exception as error:
        raise ExchangeRateError("Não foi possível consultar a cotação do PTAX.") from error
    quotes = payload.get("value") if isinstance(payload, dict) else None
    if not quotes:
        raise ExchangeRateError("O PTAX não publicou cotação no período.")
    latest = quotes[0]
    return float(latest["cotacaoVenda"]), str(latest["dataHoraCotacao"])
