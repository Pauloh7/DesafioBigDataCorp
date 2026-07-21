import argparse
import csv
import json
import sys
import unicodedata
from contextlib import contextmanager
from collections.abc import Generator
from pathlib import Path
from typing import TextIO
from datetime import datetime
from typing import Any
from __future__ import annotations

CLUBS_CSV_COLUMNS = [
    "Id do Clube",
    "Nome",
    "Campeonato",
    "Data de Fundação",
    "Cidade",
    "Estado",
    "País",
    "Estádio",
    "Presidente",
    "Apelido",
    "Cores",
]

PLAYERS_CSV_COLUMNS = [
    "Id do Clube",
    "Id do Jogador",
    "Nome",
    "Idade",
    "Gols",
    "Data de Estreia",
    "Posição",
    "Número da Camisa",
]


def empty_if_null(value: Any) -> Any:
    """Campos ausentes ou nulos viram campo vazio no CSV."""
    return "" if value is None else value


def normalize_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""

    without_accents = "".join(
        character
        for character in unicodedata.normalize("NFKD", value)
        if not unicodedata.combining(character)
    )

    return " ".join(without_accents.upper().split())


def is_allowed_championship(value: Any) -> bool:
    return normalize_text(value) in {"SERIE A", "SERIE B"}

def valid_date_or_empty(value: Any) -> str:
    """Mantém somente datas válidas no formato YYYY-MM-DD."""
    if not isinstance(value, str):
        return ""

    try:
        parsed_date = datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return ""

    # Garante que o formato original seja exatamente YYYY-MM-DD.
    if parsed_date.strftime("%Y-%m-%d") != value:
        return ""

    return value

def join_colors(value: Any) -> str:
    """Transforma ['preto', 'branco'] em preto|branco."""
    if not isinstance(value, list):
        return ""

    colors = []

    for color in value:
        if color is None:
            continue

        if isinstance(color, (str, int, float, bool)):
            colors.append(str(color))

    return "|".join(colors)


def club_to_csv_row(club: dict[str, Any]) -> dict[str, Any]:
    return {
        "Id do Clube": empty_if_null(club.get("club_id")),
        "Nome": empty_if_null(club.get("name")),
        "Campeonato": empty_if_null(club.get("championship")),
        "Data de Fundação": valid_date_or_empty(
            club.get("founding_date")
        ),
        "Cidade": empty_if_null(club.get("city")),
        "Estado": empty_if_null(club.get("state")),
        "País": empty_if_null(club.get("country")),
        "Estádio": empty_if_null(club.get("stadium")),
        "Presidente": empty_if_null(club.get("president")),
        "Apelido": empty_if_null(club.get("nickname")),
        "Cores": join_colors(club.get("colors")),
    }


@contextmanager
def open_processing_files(
    input_path: Path,
    output_path: Path,
) -> Generator[
    tuple[TextIO, TextIO, TextIO],
    None,
    None,
]:
    if not input_path.is_file():
        raise FileNotFoundError(
            f"Arquivo de entrada não encontrado: {input_path}"
        )

    output_path.mkdir(parents=True, exist_ok=True)

    clubs_output_path = output_path / "clubs.csv"
    players_output_path = output_path / "players.csv"

    with (
        input_path.open(
            mode="r",
            encoding="utf-8",
        ) as input_file,
        clubs_output_path.open(
            mode="w",
            encoding="utf-8",
            newline="",
        ) as clubs_file,
        players_output_path.open(
            mode="w",
            encoding="utf-8",
            newline="",
        ) as players_file,
    ):
        yield input_file, clubs_file, players_file


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Processa um arquivo JSONL de clubes."
    )

    parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="Caminho do arquivo JSONL de entrada.",
    )

    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Pasta onde clubs.csv e players.csv serão gerados.",
    )

    return parser.parse_args()


def process_clubs_file(
    input_path: Path,
    output_path: Path,
) -> None:
    with open_processing_files(
        input_path,
        output_path,
    ) as (input_file, clubs_file, players_file):

        clubs_writer = csv.DictWriter(
            clubs_file,
            fieldnames=CLUBS_CSV_COLUMNS,
            delimiter=",",
            quoting=csv.QUOTE_MINIMAL,
            lineterminator="\n",
        )

        players_writer = csv.DictWriter(
            players_file,
            fieldnames=PLAYERS_CSV_COLUMNS,
            delimiter=",",
            quoting=csv.QUOTE_MINIMAL,
            lineterminator="\n",
        )

        clubs_writer.writeheader()
        players_writer.writeheader()

        for line_number, raw_line in enumerate(
            input_file,
            start=1,
        ):
            if not raw_line.strip():
                continue

            try:
                club = json.loads(raw_line)
            except json.JSONDecodeError as error:
                skipped += 1
                print(
                    f"Linha {line_number} ignorada: "
                    f"JSON inválido ({error}).",
                    file=sys.stderr,
                )
                continue

            if not isinstance(club, dict):
                skipped += 1
                print(
                    f"Linha {line_number} ignorada: "
                    "o registro não é um objeto JSON.",
                    file=sys.stderr,
                )
                continue

            # Clubes de outros campeonatos não entram no CSV.
            if not is_allowed_championship(
                club.get("championship")
            ):
                continue

            try:
                clubs_writer.writerow(club_to_csv_row(club))
                written += 1
            except (TypeError, ValueError, csv.Error) as error:
                skipped += 1
                print(
                    f"Linha {line_number} ignorada: "
                    f"registro problemático ({error}).",
                    file=sys.stderr,
                )

    return written, skipped

if __name__ == "__main__":
    arguments = parse_arguments()

    process_clubs_file(
        input_path=arguments.input,
        output_path=arguments.output,
    )