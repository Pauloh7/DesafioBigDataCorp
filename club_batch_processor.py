from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import unicodedata
from collections.abc import Generator, Iterator
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
    """Armazena as estatísticas acumuladas durante o processamento.

    Attributes:
        lines_read (int): Quantidade total de linhas lidas do arquivo JSONL.
        blank_lines (int): Quantidade de linhas vazias encontradas.
        clubs_written (int): Quantidade de clubes escritos em ``clubs.csv``.
        players_written (int): Quantidade de jogadores escritos em ``players.csv``.
        filtered_clubs (int): Quantidade de clubes removidos pelo filtro de campeonato.
        invalid_records (int): Quantidade de registros ou estruturas inválidas encontradas.
    """

    lines_read: int = 0
    blank_lines: int = 0
    clubs_written: int = 0
    players_written: int = 0
    filtered_clubs: int = 0
    invalid_records: int = 0


@dataclass(slots=True)
class ErrorReporter:
    """Controla a exibição de mensagens de erro durante o processamento.

    Attributes:
        limit (int): Quantidade máxima de mensagens exibidas individualmente.
        shown (int): Quantidade de mensagens já exibidas.
        suppressed (int): Quantidade de mensagens omitidas após atingir o limite.
    """

    limit: int
    shown: int = 0
    suppressed: int = 0

    def report(self, message: str) -> None:
        """Exibe ou contabiliza uma mensagem de erro.

        Args:
            message (str): Mensagem de erro que deve ser registrada.

        Returns:
            None: O método apenas atualiza os contadores e escreve no stderr.
        """
        if self.shown < self.limit:
            print(message, file=sys.stderr)
            self.shown += 1
        else:
            self.suppressed += 1

    def print_summary(self) -> None:
        """Exibe a quantidade de mensagens de erro suprimidas.

        Returns:
            None: O método apenas escreve o resumo no stderr quando necessário.
        """
        if self.suppressed:
            print(
                f"Mensagens de erro suprimidas: {self.suppressed}.",
                file=sys.stderr,
            )


def text_or_empty(value: Any) -> str:
    """Retorna o valor somente quando ele for textual.

    Args:
        value (Any): Valor que será validado.

    Returns:
        str: O texto recebido ou uma string vazia para tipos incompatíveis.
    """
    return value if isinstance(value, str) else ""


def integer_or_empty(value: Any) -> int | str:
    """Retorna o valor somente quando ele for um número inteiro válido.

    Args:
        value (Any): Valor que será validado.

    Returns:
        int | str: O inteiro recebido ou uma string vazia para tipos incompatíveis.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        return ""

    return value


@lru_cache(maxsize=32)
def normalize_text(value: str) -> str:
    """Normaliza um texto para comparação sem acentos e sem espaços extras.

    Args:
        value (str): Texto original que será normalizado.

    Returns:
        str: Texto em maiúsculas, sem acentos e com espaços normalizados.
    """
    normalized = unicodedata.normalize("NFKD", value)
    without_accents = "".join(
        character for character in normalized if not unicodedata.combining(character)
    )
    return " ".join(without_accents.upper().split())


def is_allowed_championship(value: Any) -> bool:
    """Verifica se o campeonato pertence à Série A ou à Série B.

    Args:
        value (Any): Campeonato informado no registro do clube.

    Returns:
        bool: ``True`` quando o campeonato é permitido; caso contrário, ``False``.
    """
    return isinstance(value, str) and normalize_text(value) in ALLOWED_CHAMPIONSHIPS


def valid_date_or_empty(value: Any) -> str:
    """Valida uma data no formato ISO ``yyyy-MM-dd``.

    Args:
        value (Any): Valor de data recebido do JSON.

    Returns:
        str: A data original quando válida ou uma string vazia quando inválida.
    """
    if not isinstance(value, str):
        return ""

    try:
        parsed_date = date.fromisoformat(value)
    except ValueError:
        return ""

    return value if parsed_date.isoformat() == value else ""


def join_colors(value: Any) -> str:
    """Une as cores válidas de uma lista utilizando ``|`` como separador.

    Args:
        value (Any): Valor esperado para o campo ``colors``.

    Returns:
        str: Cores textuais unidas por ``|`` ou uma string vazia.
    """
    if not isinstance(value, list):
        return ""

    return "|".join(color for color in value if isinstance(color, str))


def club_to_csv_row(club: dict[str, Any]) -> dict[str, Any]:
    """Converte um clube do JSON para o formato esperado em ``clubs.csv``.

    Args:
        club (dict[str, Any]): Objeto JSON que representa um clube.

    Returns:
        dict[str, Any]: Linha pronta para ser escrita pelo ``csv.DictWriter``.
    """
    return {
        "Id do Clube": text_or_empty(club.get("club_id")),
        "Nome": text_or_empty(club.get("name")),
        "Campeonato": text_or_empty(club.get("championship")),
        "Data de Fundação": valid_date_or_empty(club.get("founding_date")),
        "Cidade": text_or_empty(club.get("city")),
        "Estado": text_or_empty(club.get("state")),
        "País": text_or_empty(club.get("country")),
        "Estádio": text_or_empty(club.get("stadium")),
        "Presidente": text_or_empty(club.get("president")),
        "Apelido": text_or_empty(club.get("nickname")),
        "Cores": join_colors(club.get("colors")),
    }


def player_to_csv_row(
    player: dict[str, Any],
    club_id: Any,
) -> dict[str, Any]:
    """Converte um jogador do JSON para o formato de ``players.csv``.

    Args:
        player (dict[str, Any]): Objeto JSON que representa um jogador.
        club_id (Any): Identificador do clube ao qual o jogador pertence.

    Returns:
        dict[str, Any]: Linha pronta para ser escrita pelo ``csv.DictWriter``.
    """
    return {
        "Id do Clube": text_or_empty(club_id),
        "Id do Jogador": text_or_empty(player.get("player_id")),
        "Nome": text_or_empty(player.get("name")),
        "Idade": integer_or_empty(player.get("age")),
        "Gols": integer_or_empty(player.get("goals")),
        "Data de Estreia": valid_date_or_empty(player.get("debut_date")),
        "Posição": text_or_empty(player.get("position")),
        "Número da Camisa": integer_or_empty(player.get("shirt_number")),
    }


def reject_invalid_json_constant(value: str) -> None:
    """Rejeita constantes que não pertencem ao padrão JSON.

    Args:
        value (str): Constante inválida encontrada pelo parser, como ``NaN``.

    Raises:
        ValueError: Sempre, para impedir a aceitação da constante inválida.
    """
    raise ValueError(f"constante JSON inválida: {value}")


def create_csv_writer(
    file: TextIO,
    columns: list[str],
) -> csv.DictWriter:
    """Cria um escritor CSV e grava o cabeçalho do arquivo.

    Args:
        file (TextIO): Arquivo textual aberto para escrita.
        columns (list[str]): Colunas na ordem exata esperada no CSV.

    Returns:
        csv.DictWriter: Escritor configurado para produzir o arquivo CSV.
    """
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
    """Processa um arquivo JSONL de clubes e gera dois arquivos CSV.

    O processamento é realizado linha por linha para manter o consumo de memória
    constante mesmo em bases com muitos milhões de registros. Os arquivos finais
    são substituídos somente depois que o processamento termina com sucesso.

    Attributes:
        input_path (Path): Caminho do arquivo JSONL de entrada.
        output_dir (Path): Diretório no qual os arquivos CSV serão gerados.
        progress_interval (int): Intervalo de linhas para exibição do progresso.
        stats (ProcessingStats): Estatísticas acumuladas do processamento.
        errors (ErrorReporter): Controlador das mensagens de registros inválidos.
        clubs_path (Path): Caminho final do arquivo ``clubs.csv``.
        players_path (Path): Caminho final do arquivo ``players.csv``.
        clubs_temp (Path): Caminho temporário utilizado para escrever clubes.
        players_temp (Path): Caminho temporário utilizado para escrever jogadores.
    """

    def __init__(
        self,
        input_path: Path,
        output_dir: Path,
        progress_interval: int,
        max_error_messages: int,
    ) -> None:
        """Inicializa o exportador e define os caminhos de trabalho.

        Args:
            input_path (Path): Caminho do arquivo JSONL de entrada.
            output_dir (Path): Diretório dos arquivos CSV de saída.
            progress_interval (int): Intervalo usado para exibir o progresso.
            max_error_messages (int): Limite de erros mostrados individualmente.

        Returns:
            None: O método apenas inicializa o estado da instância.
        """
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
        """Executa o fluxo completo de conversão do JSONL para CSV.

        Returns:
            ProcessingStats: Estatísticas finais do processamento.

        Raises:
            OSError: Quando ocorre uma falha de leitura, escrita ou manipulação de arquivos.
            ValueError: Quando os caminhos de entrada e saída são incompatíveis.
        """
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
        """Valida os caminhos e prepara o diretório para o processamento.

        Returns:
            None: O método apenas prepara os recursos necessários.

        Raises:
            FileNotFoundError: Quando o arquivo JSONL de entrada não existe.
            ValueError: Quando o arquivo de entrada também seria usado como saída.
        """
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
        """Impede que o arquivo de entrada seja sobrescrito como saída.

        Returns:
            None: O método apenas valida os caminhos configurados.

        Raises:
            ValueError: Quando ``clubs.csv`` ou ``players.csv`` coincide com a entrada.
        """
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
        ],
        None,
        None,
    ]:
        """Abre a entrada e cria os escritores dos arquivos CSV temporários.

        Yields:
            tuple[BinaryIO, csv.DictWriter, csv.DictWriter]: Arquivo de entrada,
            escritor de clubes e escritor de jogadores.

        Raises:
            OSError: Quando algum arquivo não pode ser aberto.
        """
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
        """Percorre o arquivo de entrada e processa cada linha separadamente.

        Args:
            input_file (BinaryIO): Arquivo JSONL aberto em modo binário.
            clubs_writer (csv.DictWriter): Escritor do arquivo de clubes.
            players_writer (csv.DictWriter): Escritor do arquivo de jogadores.

        Returns:
            None: O método escreve os registros diretamente nos CSVs.
        """
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
        """Processa uma única linha do JSONL.

        Args:
            raw_line (bytes): Conteúdo bruto da linha de entrada.
            line_number (int): Número da linha no arquivo JSONL.
            clubs_writer (csv.DictWriter): Escritor do arquivo de clubes.
            players_writer (csv.DictWriter): Escritor do arquivo de jogadores.

        Returns:
            None: A linha é ignorada, filtrada ou escrita nos arquivos de saída.
        """
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
        """Decodifica e interpreta uma linha como objeto de clube.

        Args:
            raw_line (bytes): Linha bruta lida do arquivo JSONL.
            line_number (int): Número da linha usado nas mensagens de erro.

        Returns:
            dict[str, Any] | None: Clube interpretado ou ``None`` quando inválido.
        """
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
        """Decodifica uma linha em UTF-8 e remove um possível BOM inicial.

        Args:
            raw_line (bytes): Linha bruta lida do arquivo.
            line_number (int): Número da linha usado nas mensagens de erro.

        Returns:
            str | None: Texto decodificado ou ``None`` quando o UTF-8 é inválido.
        """
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
        """Converte o texto JSON em um dicionário de clube.

        Args:
            text (str): Linha textual contendo o JSON.
            line_number (int): Número da linha usado nas mensagens de erro.

        Returns:
            dict[str, Any] | None: Objeto JSON quando ele for um dicionário válido.
        """
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
        """Escreve no CSV todos os jogadores válidos de um clube.

        Args:
            club (dict[str, Any]): Clube que contém a lista de jogadores.
            line_number (int): Número da linha do clube no arquivo de entrada.
            writer (csv.DictWriter): Escritor do arquivo ``players.csv``.

        Returns:
            None: Os jogadores são escritos diretamente no arquivo de saída.
        """
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
    ) -> Iterator[dict[str, Any]]:
        """Percorre apenas os jogadores representados por objetos JSON válidos.

        Args:
            club (dict[str, Any]): Clube que contém o campo ``players``.
            line_number (int): Número da linha utilizado nas mensagens de erro.

        Yields:
            dict[str, Any]: Cada jogador válido encontrado na lista.
        """
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
        """Registra uma ocorrência inválida e encaminha sua mensagem.

        Args:
            message (str): Descrição do problema encontrado.

        Returns:
            None: O método apenas atualiza as estatísticas e o relatório.
        """
        self.stats.invalid_records += 1
        self.errors.report(message)

    def _report_progress(self) -> None:
        """Exibe o progresso ao atingir o intervalo configurado.

        Returns:
            None: O método apenas escreve a mensagem de progresso no stderr.
        """
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
        """Substitui os arquivos finais pelos arquivos temporários concluídos.

        Returns:
            None: O método move os arquivos temporários para os caminhos finais.

        Raises:
            OSError: Quando algum arquivo não pode ser substituído.
        """
        self.clubs_temp.replace(self.clubs_path)
        self.players_temp.replace(self.players_path)

    def _remove_temporary_files(self) -> None:
        """Remove arquivos temporários deixados por execuções anteriores.

        Returns:
            None: Falhas de remoção são ignoradas para não interromper o fluxo.
        """
        for path in (
            self.clubs_temp,
            self.players_temp,
        ):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass


def non_negative_integer(value: str) -> int:
    """Converte um argumento textual em inteiro não negativo.

    Args:
        value (str): Valor recebido pela linha de comando.

    Returns:
        int: Número inteiro maior ou igual a zero.

    Raises:
        argparse.ArgumentTypeError: Quando o valor não é inteiro ou é negativo.
    """
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
    """Configura e interpreta os argumentos informados pelo terminal.

    Returns:
        argparse.Namespace: Argumentos de entrada, saída, progresso e erros.
    """
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
    """Exibe no terminal o resumo final do processamento.

    Args:
        stats (ProcessingStats): Estatísticas acumuladas pelo exportador.

    Returns:
        None: O método apenas escreve o resumo na saída padrão.
    """
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
    """Executa o programa e converte exceções esperadas em códigos de saída.

    Returns:
        int: ``0`` em caso de sucesso, ``1`` para erro de processamento ou
        ``130`` quando a execução é interrompida pelo usuário.
    """
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
