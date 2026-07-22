from __future__ import annotations

import argparse
import csv
import json
import sys
import unicodedata
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, TextIO


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


@dataclass(slots=True)
class ProcessingStats:
    clubs_written: int = 0
    players_written: int = 0
    skipped_records: int = 0
    filtered_clubs: int = 0


def empty_if_null(value: Any) -> Any:
    """Transforma valores nulos em campos vazios no CSV."""
    return "" if value is None else value


def normalize_text(value: Any) -> str:
    """Remove acentos, espaços excedentes e converte para maiúsculas."""
    if not isinstance(value, str):
        return ""

    normalized_value = unicodedata.normalize("NFKD", value)

    without_accents = "".join(
        character
        for character in normalized_value
        if not unicodedata.combining(character)
    )

    return " ".join(without_accents.upper().split())


def is_allowed_championship(value: Any) -> bool:
    """Verifica se o campeonato é Série A ou Série B."""
    return normalize_text(value) in {"SERIE A", "SERIE B"}


def valid_date_or_empty(value: Any) -> str:
    """Mantém apenas datas válidas no formato YYYY-MM-DD."""
    if not isinstance(value, str):
        return ""

    try:
        parsed_date = datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return ""

    if parsed_date.strftime("%Y-%m-%d") != value:
        return ""

    return value


def join_colors(value: Any) -> str:
    if not isinstance(value, list):
        return ""

    valid_colors = [
        str(color)
        for color in value
        if isinstance(color, (str, int, float, bool))
    ]

    return "|".join(valid_colors)


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


def player_to_csv_row(
    player: dict[str, Any],
    club_id: Any,
) -> dict[str, Any]:
    """Converte um jogador do JSON para o formato do players.csv."""
    return {
        "Id do Clube": empty_if_null(club_id),
        "Id do Jogador": empty_if_null(player.get("player_id")),
        "Nome": empty_if_null(player.get("name")),
        "Idade": empty_if_null(player.get("age")),
        "Gols": empty_if_null(player.get("goals")),
        "Data de Estreia": valid_date_or_empty(
            player.get("debut_date")
        ),
        "Posição": empty_if_null(player.get("position")),
        "Número da Camisa": empty_if_null(
            player.get("shirt_number")
        ),
    }


def report_skipped(message: str) -> None:
    """Escreve mensagens de registros ignorados na saída de erro."""
    print(message, file=sys.stderr)


def parse_json_line(
    raw_line: str,
    line_number: int,
    stats: ProcessingStats,
) -> dict[str, Any] | None:
    """Converte uma linha JSONL em objeto JSON válido."""
    try:
        parsed_data = json.loads(raw_line)
    except json.JSONDecodeError as error:
        stats.skipped_records += 1

        report_skipped(
            f"Linha {line_number} ignorada: "
            f"JSON inválido ({error.msg})."
        )

        return None

    if not isinstance(parsed_data, dict):
        stats.skipped_records += 1

        report_skipped(
            f"Linha {line_number} ignorada: "
            "o registro não é um objeto JSON."
        )

        return None

    return parsed_data


@contextmanager
def open_processing_files(
    input_path: Path,
    output_path: Path,
) -> Iterator[tuple[TextIO, TextIO, TextIO]]:
    """Abre os arquivos de entrada e saída com fechamento automático."""
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


def create_csv_writer(
    file: TextIO,
    columns: list[str],
) -> csv.DictWriter:
    """Cria um escritor CSV usando as configurações do programa."""
    writer = csv.DictWriter(
        file,
        fieldnames=columns,
        delimiter=",",
        quoting=csv.QUOTE_MINIMAL,
        lineterminator="\n",
    )

    writer.writeheader()

    return writer


def write_club_players(
    club: dict[str, Any],
    players_writer: csv.DictWriter,
    line_number: int,
    stats: ProcessingStats,
) -> None:
    """Escreve os jogadores pertencentes a um clube."""
    players = club.get("players")

    if players is None:
        return

    if not isinstance(players, list):
        stats.skipped_records += 1

        report_skipped(
            f"Linha {line_number}: jogadores ignorados, "
            "pois o campo 'players' não é uma lista."
        )

        return

    club_id = club.get("club_id")

    for player_position, player in enumerate(players, start=1):
        if not isinstance(player, dict):
            stats.skipped_records += 1

            report_skipped(
                f"Linha {line_number}, jogador "
                f"{player_position} ignorado: "
                "o jogador não é um objeto JSON."
            )

            continue

        try:
            players_writer.writerow(
                player_to_csv_row(
                    player=player,
                    club_id=club_id,
                )
            )
        except (TypeError, ValueError, csv.Error) as error:
            stats.skipped_records += 1

            report_skipped(
                f"Linha {line_number}, jogador "
                f"{player_position} ignorado: {error}."
            )

            continue

        stats.players_written += 1


def process_clubs_file(
    input_path: Path,
    output_path: Path,
) -> ProcessingStats:
    """Processa o JSONL e gera os dois arquivos CSV."""
    stats = ProcessingStats()

    with open_processing_files(
        input_path=input_path,
        output_path=output_path,
    ) as (input_file, clubs_file, players_file):
        clubs_writer = create_csv_writer(
            file=clubs_file,
            columns=CLUBS_CSV_COLUMNS,
        )

        players_writer = create_csv_writer(
            file=players_file,
            columns=PLAYERS_CSV_COLUMNS,
        )

        for line_number, raw_line in enumerate(input_file, start=1):
            if not raw_line.strip():
                continue

            club = parse_json_line(
                raw_line=raw_line,
                line_number=line_number,
                stats=stats,
            )

            if club is None:
                continue

            if not is_allowed_championship(
                club.get("championship")
            ):
                stats.filtered_clubs += 1
                continue

            try:
                clubs_writer.writerow(club_to_csv_row(club))
            except (TypeError, ValueError, csv.Error) as error:
                stats.skipped_records += 1

                report_skipped(
                    f"Linha {line_number} ignorada: "
                    f"erro ao escrever o clube ({error})."
                )

                continue

            stats.clubs_written += 1

            write_club_players(
                club=club,
                players_writer=players_writer,
                line_number=line_number,
                stats=stats,
            )

    return stats


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Processa um arquivo JSONL de clubes e gera "
            "clubs.csv e players.csv."
        )
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
        help="Diretório onde os arquivos CSV serão gerados.",
    )

    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()

    try:
        stats = process_clubs_file(
            input_path=arguments.input,
            output_path=arguments.output,
        )
    except (FileNotFoundError, PermissionError, OSError) as error:
        print(f"Erro ao processar arquivos: {error}", file=sys.stderr)
        return 1

    print(
        "Processamento concluído: "
        f"{stats.clubs_written} clubes escritos, "
        f"{stats.players_written} jogadores escritos, "
        f"{stats.filtered_clubs} clubes filtrados e "
        f"{stats.skipped_records} registros ignorados."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())