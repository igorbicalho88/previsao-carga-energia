"""Modelos de previsão da carga diária de energia (SIN) para os próximos dias.

Três abordagens, do mais simples ao mais sofisticado, e uma combinação:
  - ingenuo:    repete a última semana (referência mínima que qualquer modelo deve vencer);
  - harmonica:  regressão linear com tendência, dia da semana, ciclo anual (senos e cossenos) e feriados;
  - boosting:   gradient boosting que parte do nível da última semana e aprende quanto cada dia
                do futuro se afasta dele, conforme o calendário;
  - combinado:  média da harmônica com o boosting.
"""
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge

from .feriados import calendario

INICIO_DEFINICAO_ATUAL = "2023-04-29"  # ONS passa a incluir a micro e minigeração distribuída
HORIZONTE = 14


def carregar_sin(caminho="../data/processed/carga_diaria.csv"):
    """Série diária da carga do Brasil (SIN), só no período com a definição atual."""
    dados = pd.read_csv(caminho, index_col="data", parse_dates=True)
    return dados["SIN"][INICIO_DEFINICAO_ATUAL:].asfreq("D")


def variaveis_calendario(datas):
    """Tendência, dia da semana, ciclo anual e feriados de cada data."""
    datas = pd.DatetimeIndex(datas)
    cal = calendario(datas).set_index("data")
    X = pd.DataFrame(index=datas)
    X["tendencia"] = (datas - pd.Timestamp("2023-01-01")).days / 365.25
    for d in range(7):
        X[f"dia_sem_{d}"] = (datas.dayofweek == d).astype(int)
    dia_ano = datas.dayofyear
    for k in (1, 2, 3, 4):  # ondas de 12, 6, 4 e 3 meses
        X[f"sen_{k}"] = np.sin(2 * np.pi * k * dia_ano / 365.25)
        X[f"cos_{k}"] = np.cos(2 * np.pi * k * dia_ano / 365.25)
    X["feriado"] = cal["feriado"].values
    X["meio_feriado"] = cal["meio_feriado"].values
    X["ponte"] = cal["ponte"].values
    X["feriado_dia_util"] = X["feriado"] * (datas.dayofweek < 5)
    return X


# ---------------------------------------------------------------------------
# 1) Ingênuo: repete a última semana
# ---------------------------------------------------------------------------
def prever_ingenuo(historico, horizonte=HORIZONTE):
    ultima_semana = historico.iloc[-7:].values
    datas = pd.date_range(historico.index[-1] + pd.Timedelta(days=1), periods=horizonte)
    return pd.Series([ultima_semana[i % 7] for i in range(horizonte)], index=datas)


# ---------------------------------------------------------------------------
# 2) Regressão harmônica
# ---------------------------------------------------------------------------
def prever_harmonica(historico, horizonte=HORIZONTE):
    """Ajusta log(carga) = tendência + semana + ciclo anual + feriados e projeta o futuro."""
    modelo = Ridge(alpha=1.0).fit(variaveis_calendario(historico.index), np.log(historico.values))
    datas = pd.date_range(historico.index[-1] + pd.Timedelta(days=1), periods=horizonte)
    return pd.Series(np.exp(modelo.predict(variaveis_calendario(datas))), index=datas)


# ---------------------------------------------------------------------------
# 3) Gradient boosting a partir do nível recente
# ---------------------------------------------------------------------------
CALENDARIO_BOOSTING = ["dia_sem_0", "dia_sem_1", "dia_sem_2", "dia_sem_3", "dia_sem_4", "dia_sem_5", "dia_sem_6",
                       "sen_1", "cos_1", "sen_2", "cos_2", "feriado", "meio_feriado", "ponte", "feriado_dia_util"]


def tabela_boosting(serie_log, origens, horizonte=HORIZONTE, com_alvo=True):
    """Uma linha para cada (dia da previsão, dias à frente). Tudo é medido em relação ao
    nível da última semana conhecida, então o modelo aprende padrões e não valores absolutos."""
    fim = max(origens) + pd.Timedelta(days=horizonte)
    cal = variaveis_calendario(pd.date_range(serie_log.index.min(), fim))
    linhas = []
    for origem in origens:
        historico = serie_log[:origem]
        nivel = historico.iloc[-7:].mean()
        for h in range(1, horizonte + 1):
            data = origem + pd.Timedelta(days=h)
            semanas = int(np.ceil(h / 7)) * 7  # mesmo dia da semana mais recente já conhecido
            linha = {"origem": origem, "data": data, "nivel": nivel, "dias_a_frente": h,
                     "mesmo_dia_semana_passada": serie_log.get(data - pd.Timedelta(days=semanas), np.nan) - nivel,
                     "ultimo_dia": historico.iloc[-1] - nivel,
                     "tendencia_4_semanas": nivel - historico.iloc[-28:].mean()}
            linha.update(cal.loc[data, CALENDARIO_BOOSTING].to_dict())
            if com_alvo:
                linha["alvo"] = serie_log.get(data, np.nan) - nivel
            linhas.append(linha)
    return pd.DataFrame(linhas)


VARIAVEIS_BOOSTING = ["dias_a_frente", "mesmo_dia_semana_passada", "ultimo_dia", "tendencia_4_semanas"] + \
                     CALENDARIO_BOOSTING


def novo_boosting():
    return HistGradientBoostingRegressor(max_iter=300, learning_rate=0.05, max_leaf_nodes=15,
                                         min_samples_leaf=30, random_state=42)


def prever_boosting(historico, horizonte=HORIZONTE, tabela_treino=None):
    serie_log = np.log(historico)
    if tabela_treino is None:
        tabela_treino = tabela_boosting(serie_log, serie_log.index[35:], horizonte)
    treino = tabela_treino[tabela_treino["data"] <= historico.index[-1]].dropna(subset=["alvo"])
    modelo = novo_boosting().fit(treino[VARIAVEIS_BOOSTING], treino["alvo"])
    futuro = tabela_boosting(serie_log, [historico.index[-1]], horizonte, com_alvo=False)
    previsao = np.exp(futuro["nivel"] + modelo.predict(futuro[VARIAVEIS_BOOSTING]))
    return pd.Series(previsao.values, index=pd.DatetimeIndex(futuro["data"]))


# ---------------------------------------------------------------------------
# 4) Combinação
# ---------------------------------------------------------------------------
def prever_combinado(historico, horizonte=HORIZONTE, tabela_treino=None):
    return (prever_harmonica(historico, horizonte) + prever_boosting(historico, horizonte, tabela_treino)) / 2


# ---------------------------------------------------------------------------
# Validação como na vida real (backtesting)
# ---------------------------------------------------------------------------
def backtest(serie, origens, horizonte=HORIZONTE):
    """Para cada data de origem, treina só com o passado e prevê os próximos dias.
    Retorna uma linha por (origem, dia previsto) com o valor real e a previsão de cada modelo."""
    tabela = tabela_boosting(np.log(serie), serie.index[35:], horizonte)  # montada uma vez só
    resultados = []
    for origem in origens:
        historico = serie[:origem]
        real = serie.reindex(pd.date_range(origem + pd.Timedelta(days=1), periods=horizonte))
        if real.isna().any():
            continue
        prev = pd.DataFrame({
            "real": real,
            "ingenuo": prever_ingenuo(historico, horizonte),
            "harmonica": prever_harmonica(historico, horizonte),
            "boosting": prever_boosting(historico, horizonte, tabela),
        })
        prev["combinado"] = (prev["harmonica"] + prev["boosting"]) / 2
        prev["origem"] = origem
        prev["dias_a_frente"] = range(1, horizonte + 1)
        resultados.append(prev)
    return pd.concat(resultados).rename_axis("data").reset_index()


MODELOS = ["ingenuo", "harmonica", "boosting", "combinado"]


def mape(resultado, modelos=MODELOS):
    """Erro percentual absoluto médio de cada modelo."""
    return pd.Series({m: ((resultado[m] - resultado["real"]).abs() / resultado["real"]).mean() * 100
                      for m in modelos})
