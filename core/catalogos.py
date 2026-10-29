"""Catálogos de países (con continente) y DIVIPOLA (departamento - municipio)."""
from functools import lru_cache

import pandas as pd

from .config import CATALOGOS_DIR, CONTINENTE_FORZADO


@lru_cache
def cargar_paises() -> pd.DataFrame:
    df = pd.read_csv(CATALOGOS_DIR / "paises.csv", dtype=str)
    for pais, cont in CONTINENTE_FORZADO.items():
        df.loc[df["pais"] == pais, "continente"] = cont
    return df


@lru_cache
def cargar_divipola() -> pd.DataFrame:
    return pd.read_csv(CATALOGOS_DIR / "divipola.csv", dtype=str)


def continentes() -> list[str]:
    return sorted(cargar_paises()["continente"].unique())


def paises_de(continente: str) -> list[str]:
    df = cargar_paises()
    return sorted(df.loc[df["continente"] == continente, "pais"])


def departamentos() -> list[str]:
    return sorted(cargar_divipola()["departamento"].unique())


def municipios_de(dep: str) -> list[str]:
    df = cargar_divipola()
    return sorted(df.loc[df["departamento"] == dep, "municipio"])
