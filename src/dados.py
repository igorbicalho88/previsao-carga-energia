"""Download e tratamento dos dados de carga diária do ONS (mesma lógica do notebook 01)."""
from datetime import date
from pathlib import Path

import pandas as pd

URL_ONS = "https://ons-aws-prod-opendata.s3.amazonaws.com/dataset/carga_energia_di/CARGA_ENERGIA_{ano}.csv"
PASTA = Path(__file__).resolve().parents[1] / "data"


def baixar(ano_inicial=2010, ano_final=None):
    """Baixa os arquivos anuais do ONS e salva tudo em data/raw/carga_energia_diaria.csv."""
    ano_final = ano_final or date.today().year
    bruto = pd.concat([pd.read_csv(URL_ONS.format(ano=ano), sep=";") for ano in range(ano_inicial, ano_final + 1)],
                      ignore_index=True)
    (PASTA / "raw").mkdir(parents=True, exist_ok=True)
    bruto.to_csv(PASTA / "raw" / "carga_energia_diaria.csv", index=False)
    return bruto


def tratar(bruto):
    """Corrige datas, remove vazios e duplicadas, preenche dias faltantes e soma o Brasil (SIN)."""
    bruto = bruto.copy()
    bruto["data"] = pd.to_datetime(bruto["din_instante"].str[:10])
    limpo = (bruto.dropna(subset=["val_cargaenergiamwmed"])
                  .drop_duplicates(["id_subsistema", "data"]))
    regioes = (limpo.pivot(index="data", columns="nom_subsistema", values="val_cargaenergiamwmed")
                    .asfreq("D").interpolate())
    regioes["SIN"] = regioes.sum(axis=1)
    (PASTA / "processed").mkdir(parents=True, exist_ok=True)
    regioes.to_csv(PASTA / "processed" / "carga_diaria.csv")
    return regioes
