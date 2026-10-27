"""Feriados nacionais do Brasil e dias especiais que mudam o consumo de energia.

Não depende de bibliotecas externas: os feriados móveis (Carnaval, Sexta-feira Santa
e Corpus Christi) são calculados a partir da data da Páscoa.
"""
from datetime import date, timedelta

import pandas as pd


def pascoa(ano):
    """Data da Páscoa (algoritmo de Meeus/Jones/Butcher, calendário gregoriano)."""
    a, b, c = ano % 19, ano // 100, ano % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes = (h + l - 7 * m + 114) // 31
    dia = (h + l - 7 * m + 114) % 31 + 1
    return date(ano, mes, dia)


def dias_especiais(ano):
    """Retorna {data: nome} com os feriados nacionais e datas que alteram a carga."""
    p = pascoa(ano)
    dias = {
        date(ano, 1, 1): "Confraternização Universal",
        p - timedelta(days=48): "Carnaval (segunda)",
        p - timedelta(days=47): "Carnaval (terça)",
        p - timedelta(days=46): "Quarta-feira de Cinzas",
        p - timedelta(days=2): "Sexta-feira Santa",
        date(ano, 4, 21): "Tiradentes",
        date(ano, 5, 1): "Dia do Trabalho",
        p + timedelta(days=60): "Corpus Christi",
        date(ano, 9, 7): "Independência",
        date(ano, 10, 12): "Nossa Senhora Aparecida",
        date(ano, 11, 2): "Finados",
        date(ano, 11, 15): "Proclamação da República",
        date(ano, 12, 24): "Véspera de Natal",
        date(ano, 12, 25): "Natal",
        date(ano, 12, 31): "Véspera de Ano Novo",
    }
    if ano >= 2024:  # Dia da Consciência Negra virou feriado nacional (Lei 14.759/2023)
        dias[date(ano, 11, 20)] = "Consciência Negra"
    return dias


def calendario(datas):
    """Para cada data, indica feriado, véspera/meio feriado e 'ponte' (dia entre feriado e fim de semana)."""
    datas = pd.to_datetime(pd.Series(datas)).dt.normalize()
    especiais = {}
    for ano in range(datas.dt.year.min() - 1, datas.dt.year.max() + 2):
        especiais.update({pd.Timestamp(d): n for d, n in dias_especiais(ano).items()})
    meio = {"Quarta-feira de Cinzas", "Véspera de Natal", "Véspera de Ano Novo"}
    feriados_inteiros = {d for d, n in especiais.items() if n not in meio}

    nome = datas.map(especiais)
    feriado = datas.isin(feriados_inteiros).astype(int)
    meio_feriado = nome.isin(meio).astype(int)
    # Ponte: segunda antes de feriado na terça, ou sexta depois de feriado na quinta
    ponte = (((datas.dt.dayofweek == 0) & (datas + pd.Timedelta(days=1)).isin(feriados_inteiros)) |
             ((datas.dt.dayofweek == 4) & (datas - pd.Timedelta(days=1)).isin(feriados_inteiros)))
    ponte = (ponte & (feriado == 0)).astype(int)
    return pd.DataFrame({"data": datas.values, "feriado": feriado.values, "meio_feriado": meio_feriado.values,
                         "ponte": ponte.values, "nome_feriado": nome.values})
