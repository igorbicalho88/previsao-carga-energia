"""Previsão da carga de energia do Brasil (SIN) para os próximos 14 dias.

Uso (com o ambiente ativo, na pasta do projeto):
    python prever.py                 baixa os dados mais recentes do ONS e prevê
    python prever.py --sem-download  usa os dados já baixados em data/raw

Gera:
    reports/previsao_14_dias.csv     previsão por dia (MWmed), com o feriado quando houver
    reports/figures/previsao_14_dias.png
"""
import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

from src.dados import PASTA, baixar, tratar
from src.feriados import calendario
from src.modelos import INICIO_DEFINICAO_ATUAL, prever_combinado

RAIZ = Path(__file__).resolve().parent
DIAS_SEMANA = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]


def main():
    p = argparse.ArgumentParser(description="Prevê a carga de energia do Brasil para os próximos 14 dias.")
    p.add_argument("--sem-download", action="store_true", help="usa os dados já baixados")
    a = p.parse_args()

    if a.sem_download:
        bruto = pd.read_csv(PASTA / "raw" / "carga_energia_diaria.csv")
    else:
        print("Baixando os dados do ONS...")
        bruto = baixar()
    sin = tratar(bruto)["SIN"][INICIO_DEFINICAO_ATUAL:]
    print(f"Dados até {sin.index.max():%d/%m/%Y} ({len(sin)} dias usados no treino)")

    previsao = prever_combinado(sin)
    cal = calendario(previsao.index).set_index("data")
    tabela = pd.DataFrame({
        "data": previsao.index.strftime("%d/%m/%Y"),
        "dia_semana": [DIAS_SEMANA[d] for d in previsao.index.dayofweek],
        "carga_prevista_mwmed": previsao.round(0).astype(int).values,
        "feriado": cal["nome_feriado"].fillna("").values,
    })
    (RAIZ / "reports" / "figures").mkdir(parents=True, exist_ok=True)
    tabela.to_csv(RAIZ / "reports" / "previsao_14_dias.csv", index=False, sep=";", encoding="utf-8-sig")

    fig, ax = plt.subplots(figsize=(11, 4))
    ax.plot(sin[-28:] / 1000, color="black", marker=".", label="realizado (últimas 4 semanas)")
    ax.plot(previsao / 1000, color="green", marker="o", label="previsão")
    for d, nome in cal["nome_feriado"].dropna().items():
        ax.annotate(nome, (d, previsao[d] / 1000), textcoords="offset points", xytext=(0, -15),
                    ha="center", fontsize=8, color="darkred")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m"))
    ax.set_title(f"Carga de energia do Brasil: previsão para {previsao.index[0]:%d/%m} a {previsao.index[-1]:%d/%m/%Y} "
                 "(mil MWmed)")
    ax.legend()
    plt.tight_layout()
    plt.savefig(RAIZ / "reports" / "figures" / "previsao_14_dias.png", dpi=120)

    print(tabela.to_string(index=False))
    print("\nSalvo em reports/previsao_14_dias.csv e reports/figures/previsao_14_dias.png")


if __name__ == "__main__":
    main()
