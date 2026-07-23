"""
Converte um arquivo JSONL de clubes em dois arquivos CSV:

- clubs.csv: um registro por clube;
- players.csv: um registro por jogador, relacionado ao clube pelo ID.

Política adotada para dados inválidos:
- clubes fora da Série A ou Série B são filtrados com seus jogadores;
- linhas com UTF-8 inválido, JSON inválido ou JSON que não seja objeto
  são ignoradas;
- campos escalares ausentes, nulos ou com tipos incompatíveis viram vazio;
- datas inválidas viram vazio;
- entradas inválidas em "colors" são ignoradas, e as válidas são unidas por "|";
- clube sem "players" continua sendo exportado;
- se "players" não for uma lista, o clube é mantido e os jogadores são ignorados;
- jogador que não seja objeto JSON é ignorado sem descartar o clube;
- arquivos finais só substituem os anteriores após processamento bem-sucedido.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
import unicodedata
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any, BinaryIO, TextIO

FILE_BUFFER_SIZE = 1024 * 1024
DEFAULT_PROGRESS_INTERVAL = 100_000
DEFAULT_MAX_ERROR_MESSAGES = 100

ALLOWED_CHAMPIONSHIPS = {"SERIE A", "SERIE B"}
SCALAR_TYPES = (str, int, float, bool)

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
    lines_read: int = 0
    blank_lines: int = 0
    clubs_written: int = 0
    players_written: int = 0
    filtered_clubs: int = 0
    invalid_records: int = 0


@dataclass(slots=True)
class ErrorReporter:
    limit: int
    shown: int = 0
    suppressed: int = 0

    def report(self, message: str) -> None:
        if self.shown < self.limit:
            print(message, file=sys.stderr)
            self.shown += 1
        else:
            self.suppressed += 1

    def print_summary(self) -> None:
        if self.suppressed:
            print(
                f"Mensagens de erro suprimidas: {self.suppressed}.",
                file=sys.stderr,
            )


def is_csv_scalar(value: Any) -> bool:
    if not isinstance(value, SCALAR_TYPES):
        return False

    return not (isinstance(value, float) and not math.isfinite(value))


def scalar_or_empty(value: Any) -> str | int | float | bool:
    return value if is_csv_scalar(value) else ""


@lru_cache(maxsize=32)
def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    without_accents = "".join(
        character for character in normalized if not unicodedata.combining(character)
    )
    return " ".join(without_accents.upper().split())


def is_allowed_championship(value: Any) -> bool:
    return isinstance(value, str) and normalize_text(value) in ALLOWED_CHAMPIONSHIPS


def valid_date_or_empty(value: Any) -> str:
    if not isinstance(value, str):
        return ""

    try:
        parsed_date = date.fromisoformat(value)
    except ValueError:
        return ""

    return value if parsed_date.isoformat() == value else ""


def join_colors(value: Any) -> str:
    if not isinstance(value, list):
        return ""

    return "|".join(str(color) for color in value if is_csv_scalar(color))


def club_to_csv_row(club: dict[str, Any]) -> dict[str, Any]:
    return {
        "Id do Clube": scalar_or_empty(club.get("club_id")),
        "Nome": scalar_or_empty(club.get("name")),
        "Campeonato": scalar_or_empty(club.get("championship")),
        "Data de Fundação": valid_date_or_empty(club.get("founding_date")),
        "Cidade": scalar_or_empty(club.get("city")),
        "Estado": scalar_or_empty(club.get("state")),
        "País": scalar_or_empty(club.get("country")),
        "Estádio": scalar_or_empty(club.get("stadium")),
        "Presidente": scalar_or_empty(club.get("president")),
        "Apelido": scalar_or_empty(club.get("nickname")),
        "Cores": join_colors(club.get("colors")),
    }


def player_to_csv_row(
    player: dict[str, Any],
    club_id: Any,
) -> dict[str, Any]:
    return {
        "Id do Clube": scalar_or_empty(club_id),
        "Id do Jogador": scalar_or_empty(player.get("player_id")),
        "Nome": scalar_or_empty(player.get("name")),
        "Idade": scalar_or_empty(player.get("age")),
        "Gols": scalar_or_empty(player.get("goals")),
        "Data de Estreia": valid_date_or_empty(player.get("debut_date")),
        "Posição": scalar_or_empty(player.get("position")),
        "Número da Camisa": scalar_or_empty(player.get("shirt_number")),
    }


def reject_invalid_json_constant(value: str) -> None:
    raise ValueError(f"constante JSON inválida: {value}")


def create_csv_writer(
    file: TextIO,
    columns: list[str],
) -> csv.DictWriter:
    writer = csv.DictWriter(
        file,
        fieldnames=columns,
        delimiter=",",
        quoting=csv.QUOTE_MINIMAL,
        lineterminator="\n",
    )
    writer.writeheader()
    return writer


class JsonlCsvExporter:
    def __init__(
        self,
        input_path: Path,
        output_dir: Path,
        progress_interval: int,
        max_error_messages: int,
    ) -> None:
        self.input_path = input_path
        self.output_dir = output_dir
        self.progress_interval = progress_interval

        self.stats = ProcessingStats()
        self.errors = ErrorReporter(max_error_messages)

        process_id = os.getpid()

        self.clubs_path = output_dir / "clubs.csv"
        self.players_path = output_dir / "players.csv"
        self.clubs_temp = output_dir / f".clubs.{process_id}.csv.tmp"
        self.players_temp = output_dir / f".players.{process_id}.csv.tmp"

    def run(self) -> ProcessingStats:
        self._prepare()

        try:
            with self._open_files() as files:
                self._process_file(*files)

            self._commit()
        except BaseException:
            self._remove_temporary_files()
            raise

        self.errors.print_summary()
        return self.stats

    def _prepare(self) -> None:
        if not self.input_path.is_file():
            raise FileNotFoundError(
                "Arquivo de entrada não encontrado: " f"{self.input_path}"
            )

        self.output_dir.mkdir(
            parents=True,
            exist_ok=True,
        )
        self._validate_output_paths()
        self._remove_temporary_files()

    def _validate_output_paths(self) -> None:
        resolved_input = self.input_path.resolve()

        for output_path in (
            self.clubs_path,
            self.players_path,
        ):
            if resolved_input == output_path.resolve():
                raise ValueError(
                    "O arquivo de entrada não pode ser também "
                    f"um arquivo de saída: {output_path}"
                )

    @contextmanager
    def _open_files(
        self,
    ) -> Generator[
        tuple[
            BinaryIO,
            csv.DictWriter,
            csv.DictWriter,
        ]
    ]:
        with (
            self.input_path.open(
                "rb",
                buffering=FILE_BUFFER_SIZE,
            ) as input_file,
            self.clubs_temp.open(
                "w",
                encoding="utf-8",
                newline="",
                buffering=FILE_BUFFER_SIZE,
            ) as clubs_file,
            self.players_temp.open(
                "w",
                encoding="utf-8",
                newline="",
                buffering=FILE_BUFFER_SIZE,
            ) as players_file,
        ):
            yield (
                input_file,
                create_csv_writer(
                    clubs_file,
                    CLUBS_CSV_COLUMNS,
                ),
                create_csv_writer(
                    players_file,
                    PLAYERS_CSV_COLUMNS,
                ),
            )

    def _process_file(
        self,
        input_file: BinaryIO,
        clubs_writer: csv.DictWriter,
        players_writer: csv.DictWriter,
    ) -> None:
        for line_number, raw_line in enumerate(
            input_file,
            start=1,
        ):
            self.stats.lines_read = line_number

            self._process_line(
                raw_line=raw_line,
                line_number=line_number,
                clubs_writer=clubs_writer,
                players_writer=players_writer,
            )

            self._report_progress()

    def _process_line(
        self,
        raw_line: bytes,
        line_number: int,
        clubs_writer: csv.DictWriter,
        players_writer: csv.DictWriter,
    ) -> None:
        if raw_line.isspace():
            self.stats.blank_lines += 1
            return

        club = self._read_club(
            raw_line=raw_line,
            line_number=line_number,
        )

        if club is None:
            return

        if not is_allowed_championship(club.get("championship")):
            self.stats.filtered_clubs += 1
            return

        clubs_writer.writerow(club_to_csv_row(club))
        self.stats.clubs_written += 1

        self._write_players(
            club=club,
            line_number=line_number,
            writer=players_writer,
        )

    def _read_club(
        self,
        raw_line: bytes,
        line_number: int,
    ) -> dict[str, Any] | None:
        text = self._decode_line(
            raw_line=raw_line,
            line_number=line_number,
        )

        if text is None:
            return None

        return self._parse_club(
            text=text,
            line_number=line_number,
        )

    def _decode_line(
        self,
        raw_line: bytes,
        line_number: int,
    ) -> str | None:
        try:
            text = raw_line.decode("utf-8")
        except UnicodeDecodeError as error:
            self._record_error(
                f"Linha {line_number} ignorada: " f"UTF-8 inválido ({error})."
            )
            return None

        if line_number == 1:
            text = text.removeprefix("\ufeff")

        return text

    def _parse_club(
        self,
        text: str,
        line_number: int,
    ) -> dict[str, Any] | None:
        try:
            club = json.loads(
                text,
                parse_constant=reject_invalid_json_constant,
            )
        except (
            json.JSONDecodeError,
            ValueError,
            RecursionError,
        ) as error:
            self._record_error(
                f"Linha {line_number} ignorada: " f"JSON inválido ({error})."
            )
            return None

        if isinstance(club, dict):
            return club

        self._record_error(
            f"Linha {line_number} ignorada: " "o registro não é um objeto JSON."
        )
        return None

    def _write_players(
        self,
        club: dict[str, Any],
        line_number: int,
        writer: csv.DictWriter,
    ) -> None:
        club_id = club.get("club_id")

        for player in self._iter_players(
            club=club,
            line_number=line_number,
        ):
            writer.writerow(
                player_to_csv_row(
                    player=player,
                    club_id=club_id,
                )
            )
            self.stats.players_written += 1

    def _iter_players(
        self,
        club: dict[str, Any],
        line_number: int,
    ) -> Generator[dict[str, Any]]:
        players = club.get("players")

        if players is None:
            return

        if not isinstance(players, list):
            self._record_error(
                f"Linha {line_number}: "
                "jogadores ignorados, pois "
                "'players' não é uma lista."
            )
            return

        for position, player in enumerate(
            players,
            start=1,
        ):
            if isinstance(player, dict):
                yield player
                continue

            self._record_error(
                f"Linha {line_number}, "
                f"jogador {position} ignorado: "
                "o jogador não é um objeto JSON."
            )

    def _record_error(self, message: str) -> None:
        self.stats.invalid_records += 1
        self.errors.report(message)

    def _report_progress(self) -> None:
        if self.progress_interval <= 0:
            return

        if self.stats.lines_read % self.progress_interval != 0:
            return

        print(
            "Progresso: "
            f"{self.stats.lines_read:,} linhas, "
            f"{self.stats.clubs_written:,} clubes e "
            f"{self.stats.players_written:,} jogadores.",
            file=sys.stderr,
        )

    def _commit(self) -> None:
        self.clubs_temp.replace(self.clubs_path)
        self.players_temp.replace(self.players_path)

    def _remove_temporary_files(self) -> None:
        for path in (
            self.clubs_temp,
            self.players_temp,
        ):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass


def non_negative_integer(value: str) -> int:
    try:
        number = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "o valor deve ser um número inteiro"
        ) from error

    if number < 0:
        raise argparse.ArgumentTypeError("o valor deve ser maior ou igual a zero")

    return number


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=("Processa um JSONL de clubes e gera " "clubs.csv e players.csv.")
    )

    parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="Arquivo JSONL de entrada.",
    )
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Diretório dos arquivos CSV.",
    )
    parser.add_argument(
        "--progress-every",
        type=non_negative_integer,
        default=DEFAULT_PROGRESS_INTERVAL,
        metavar="LINHAS",
        help=("Exibe progresso a cada N linhas; " "0 desativa."),
    )
    parser.add_argument(
        "--max-error-messages",
        type=non_negative_integer,
        default=DEFAULT_MAX_ERROR_MESSAGES,
        metavar="QUANTIDADE",
        help=("Quantidade máxima de erros " "exibidos individualmente."),
    )

    return parser.parse_args()


def print_final_summary(
    stats: ProcessingStats,
) -> None:
    print(
        "Processamento concluído: "
        f"{stats.lines_read} linhas lidas, "
        f"{stats.blank_lines} linhas vazias, "
        f"{stats.clubs_written} clubes escritos, "
        f"{stats.players_written} jogadores escritos, "
        f"{stats.filtered_clubs} clubes filtrados e "
        f"{stats.invalid_records} registros inválidos."
    )


def execute() -> int:
    arguments = parse_arguments()

    exporter = JsonlCsvExporter(
        input_path=arguments.input,
        output_dir=arguments.output,
        progress_interval=arguments.progress_every,
        max_error_messages=(arguments.max_error_messages),
    )

    try:
        stats = exporter.run()
    except KeyboardInterrupt:
        print(
            "Processamento interrompido pelo usuário.",
            file=sys.stderr,
        )
        return 130
    except (
        OSError,
        ValueError,
    ) as error:
        print(
            f"Erro ao processar arquivos: {error}",
            file=sys.stderr,
        )
        return 1

    print_final_summary(stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(execute())
