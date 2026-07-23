from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from club_batch_processor import JsonlCsvExporter, ProcessingStats


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False).encode("utf-8")


def _run_export(
    tmp_path: Path,
    lines: list[bytes],
) -> tuple[ProcessingStats, list[dict[str, str]], list[dict[str, str]]]:
    input_path = tmp_path / "sample_clubes.jsonl"
    output_dir = tmp_path / "output"

    input_path.write_bytes(b"\n".join(lines) + b"\n")

    exporter = JsonlCsvExporter(
        input_path=input_path,
        output_dir=output_dir,
        progress_interval=0,
        max_error_messages=0,
    )
    stats = exporter.run()

    with (output_dir / "clubs.csv").open(
        encoding="utf-8",
        newline="",
    ) as clubs_file:
        clubs = list(csv.DictReader(clubs_file))

    with (output_dir / "players.csv").open(
        encoding="utf-8",
        newline="",
    ) as players_file:
        players = list(csv.DictReader(players_file))

    return stats, clubs, players


def _club(
    *,
    club_id: str = "CLB-1",
    championship: str = "SERIE A",
    players: Any = None,
    **overrides: Any,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "club_id": club_id,
        "name": "Clube Teste",
        "championship": championship,
        "founding_date": "2000-01-02",
        "city": "São Paulo",
        "state": "SP",
        "country": "Brasil",
        "stadium": "Estádio Teste",
        "president": "Presidente Teste",
        "nickname": "Teste",
        "colors": ["azul", "branco"],
    }

    if players is not None:
        data["players"] = players

    data.update(overrides)
    return data


def _player(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "player_id": "JOG-1",
        "name": "Jogador Teste",
        "age": 25,
        "goals": 10,
        "debut_date": "2020-03-04",
        "position": "Atacante",
        "shirt_number": 9,
    }
    data.update(overrides)
    return data


def test_serie_a_e_exportada_com_seus_jogadores(tmp_path: Path) -> None:
    stats, clubs, players = _run_export(
        tmp_path,
        [_json_bytes(_club(championship="SERIE A", players=[_player()]))],
    )

    assert stats.clubs_written == 1
    assert stats.players_written == 1
    assert stats.filtered_clubs == 0
    assert clubs[0]["Campeonato"] == "SERIE A"
    assert players[0]["Id do Clube"] == "CLB-1"


def test_serie_b_e_exportada_com_seus_jogadores(tmp_path: Path) -> None:
    stats, clubs, players = _run_export(
        tmp_path,
        [
            _json_bytes(
                _club(
                    club_id="CLB-B",
                    championship="SERIE B",
                    players=[_player(player_id="JOG-B")],
                )
            )
        ],
    )

    assert stats.clubs_written == 1
    assert stats.players_written == 1
    assert clubs[0]["Campeonato"] == "SERIE B"
    assert players[0]["Id do Clube"] == "CLB-B"


@pytest.mark.parametrize(
    "championship",
    ["SERIE A", "SÉRIE A", "Serie B", "Série B"],
    ids=["serie-a-sem-acento", "serie-a-com-acento", "serie-b-sem-acento", "serie-b-com-acento"],
)
def test_campeonato_com_e_sem_acento_e_aceito(
    tmp_path: Path,
    championship: str,
) -> None:
    stats, clubs, _ = _run_export(
        tmp_path,
        [_json_bytes(_club(championship=championship))],
    )

    assert stats.clubs_written == 1
    assert stats.filtered_clubs == 0
    # O valor original é preservado; a normalização serve apenas para o filtro.
    assert clubs[0]["Campeonato"] == championship


def test_clube_de_outro_campeonato_e_filtrado_com_jogadores(
    tmp_path: Path,
) -> None:
    stats, clubs, players = _run_export(
        tmp_path,
        [
            _json_bytes(
                _club(
                    championship="SERIE C",
                    players=[_player()],
                )
            )
        ],
    )

    assert stats.filtered_clubs == 1
    assert stats.clubs_written == 0
    assert stats.players_written == 0
    assert clubs == []
    assert players == []


def test_datas_invalidas_viram_campos_vazios_sem_descartar_linhas(
    tmp_path: Path,
) -> None:
    stats, clubs, players = _run_export(
        tmp_path,
        [
            _json_bytes(
                _club(
                    founding_date="2023-02-30",
                    players=[_player(debut_date="04/03/2020")],
                )
            )
        ],
    )

    assert stats.clubs_written == 1
    assert stats.players_written == 1
    assert stats.invalid_records == 0
    assert clubs[0]["Data de Fundação"] == ""
    assert players[0]["Data de Estreia"] == ""


def test_json_invalido_e_ignorado_sem_abortar_processamento(
    tmp_path: Path,
) -> None:
    valid_club = _club(club_id="VALIDO")

    stats, clubs, players = _run_export(
        tmp_path,
        [b'{"club_id": "QUEBRADO",', _json_bytes(valid_club)],
    )

    assert stats.lines_read == 2
    assert stats.invalid_records == 1
    assert stats.clubs_written == 1
    assert [club["Id do Clube"] for club in clubs] == ["VALIDO"]
    assert players == []


def test_campos_ausentes_e_null_viram_vazios(tmp_path: Path) -> None:
    club = {
        "club_id": "NULL-1",
        "name": None,
        "championship": "SERIE A",
        "founding_date": None,
        # city ausente
        "state": None,
        "country": "Brasil",
        "stadium": None,
        # president ausente
        "nickname": None,
        "colors": None,
        "players": [
            {
                "player_id": "P-NULL",
                "name": None,
                # age ausente
                "goals": None,
                "debut_date": None,
                # position ausente
                "shirt_number": None,
            }
        ],
    }

    stats, clubs, players = _run_export(tmp_path, [_json_bytes(club)])

    assert stats.invalid_records == 0
    assert clubs[0] == {
        "Id do Clube": "NULL-1",
        "Nome": "",
        "Campeonato": "SERIE A",
        "Data de Fundação": "",
        "Cidade": "",
        "Estado": "",
        "País": "Brasil",
        "Estádio": "",
        "Presidente": "",
        "Apelido": "",
        "Cores": "",
    }
    assert players[0] == {
        "Id do Clube": "NULL-1",
        "Id do Jogador": "P-NULL",
        "Nome": "",
        "Idade": "",
        "Gols": "",
        "Data de Estreia": "",
        "Posição": "",
        "Número da Camisa": "",
    }


def test_clube_sem_jogadores_permanece_no_clubs_csv(tmp_path: Path) -> None:
    club = _club(club_id="SEM-JOGADORES")
    club.pop("players", None)

    stats, clubs, players = _run_export(tmp_path, [_json_bytes(club)])

    assert stats.clubs_written == 1
    assert stats.players_written == 0
    assert clubs[0]["Id do Clube"] == "SEM-JOGADORES"
    assert players == []


def test_players_que_nao_e_lista_mantem_clube_e_ignora_jogadores(
    tmp_path: Path,
) -> None:
    stats, clubs, players = _run_export(
        tmp_path,
        [_json_bytes(_club(players={"player_id": "ERRADO"}))],
    )

    assert stats.clubs_written == 1
    assert stats.players_written == 0
    assert stats.invalid_records == 1
    assert len(clubs) == 1
    assert players == []


def test_jogador_invalido_e_ignorado_mas_validos_sao_exportados(
    tmp_path: Path,
) -> None:
    stats, clubs, players = _run_export(
        tmp_path,
        [
            _json_bytes(
                _club(
                    players=[
                        "jogador inválido",
                        None,
                        _player(player_id="VALIDO-1"),
                    ]
                )
            )
        ],
    )

    assert stats.clubs_written == 1
    assert stats.players_written == 1
    assert stats.invalid_records == 2
    assert len(clubs) == 1
    assert [player["Id do Jogador"] for player in players] == ["VALIDO-1"]


def test_virgulas_e_aspas_sao_escapadas_corretamente_no_csv(
    tmp_path: Path,
) -> None:
    club_name = 'Clube, "Estrela"'
    president = 'João "Joca", Filho'
    player_name = 'Atacante, "Rápido"'

    _, clubs, players = _run_export(
        tmp_path,
        [
            _json_bytes(
                _club(
                    name=club_name,
                    president=president,
                    players=[_player(name=player_name)],
                )
            )
        ],
    )

    # A leitura com csv.DictReader deve reconstruir exatamente os valores.
    assert clubs[0]["Nome"] == club_name
    assert clubs[0]["Presidente"] == president
    assert players[0]["Nome"] == player_name

    raw_clubs = (tmp_path / "output" / "clubs.csv").read_text(encoding="utf-8")
    raw_players = (tmp_path / "output" / "players.csv").read_text(encoding="utf-8")

    assert '"Clube, ""Estrela"""' in raw_clubs
    assert '"João ""Joca"", Filho"' in raw_clubs
    assert '"Atacante, ""Rápido"""' in raw_players


def test_bom_utf8_na_primeira_linha_e_removido(tmp_path: Path) -> None:
    line_with_bom = b"\xef\xbb\xbf" + _json_bytes(
        _club(
            club_id="BOM-1",
            championship="SÉRIE A",
            players=[_player()],
        )
    )

    stats, clubs, players = _run_export(tmp_path, [line_with_bom])

    assert stats.invalid_records == 0
    assert stats.clubs_written == 1
    assert stats.players_written == 1
    assert clubs[0]["Id do Clube"] == "BOM-1"


def test_tipos_incompativeis_viram_campos_vazios(
    tmp_path: Path,
) -> None:
    club = _club(
        club_id=123,
        name=True,
        city=["São Paulo"],
        state={"sigla": "SP"},
        country=10.5,
        stadium=False,
        president=999,
        nickname=["Teste"],
        colors=["azul", 7, True, None, "branco"],
        players=[
            _player(
                player_id=456,
                name=False,
                age="25",
                goals=10.5,
                position=["Atacante"],
                shirt_number=True,
            )
        ],
    )

    stats, clubs, players = _run_export(tmp_path, [_json_bytes(club)])

    assert stats.clubs_written == 1
    assert stats.players_written == 1
    assert stats.invalid_records == 0
    assert clubs[0] == {
        "Id do Clube": "",
        "Nome": "",
        "Campeonato": "SERIE A",
        "Data de Fundação": "2000-01-02",
        "Cidade": "",
        "Estado": "",
        "País": "",
        "Estádio": "",
        "Presidente": "",
        "Apelido": "",
        "Cores": "azul|branco",
    }
    assert players[0] == {
        "Id do Clube": "",
        "Id do Jogador": "",
        "Nome": "",
        "Idade": "",
        "Gols": "",
        "Data de Estreia": "2020-03-04",
        "Posição": "",
        "Número da Camisa": "",
    }


def test_utf8_invalido_nao_impede_processamento_da_linha_seguinte(
    tmp_path: Path,
) -> None:
    stats, clubs, players = _run_export(
        tmp_path,
        [
            b"\xff\xfe\xfa",
            _json_bytes(
                _club(
                    club_id="UTF8-VALIDO",
                    players=[_player(player_id="JOG-UTF8")],
                )
            ),
        ],
    )

    assert stats.lines_read == 2
    assert stats.invalid_records == 1
    assert stats.clubs_written == 1
    assert stats.players_written == 1
    assert [club["Id do Clube"] for club in clubs] == ["UTF8-VALIDO"]
    assert [player["Id do Jogador"] for player in players] == ["JOG-UTF8"]


@pytest.mark.parametrize(
    "non_object_json",
    [[], "texto", 123, None],
    ids=["lista", "string", "numero", "null"],
)
def test_json_valido_que_nao_e_objeto_e_ignorado(
    tmp_path: Path,
    non_object_json: Any,
) -> None:
    stats, clubs, players = _run_export(
        tmp_path,
        [
            _json_bytes(non_object_json),
            _json_bytes(_club(club_id="OBJETO-VALIDO")),
        ],
    )

    assert stats.lines_read == 2
    assert stats.invalid_records == 1
    assert stats.clubs_written == 1
    assert [club["Id do Clube"] for club in clubs] == ["OBJETO-VALIDO"]
    assert players == []


def test_linhas_completamente_vazias_sao_ignoradas(tmp_path: Path) -> None:
    stats, clubs, players = _run_export(
        tmp_path,
        [
            b"",
            b"   ",
            b"\t",
            _json_bytes(_club(club_id="DEPOIS-DAS-VAZIAS")),
        ],
    )

    assert stats.lines_read == 4
    assert stats.blank_lines == 3
    assert stats.invalid_records == 0
    assert stats.clubs_written == 1
    assert [club["Id do Clube"] for club in clubs] == ["DEPOIS-DAS-VAZIAS"]
    assert players == []


def test_colors_vazio_ausente_ou_com_tipo_incorreto_vira_vazio(
    tmp_path: Path,
) -> None:
    club_without_colors = _club(club_id="CORES-AUSENTE")
    club_without_colors.pop("colors")

    clubs_to_process = [
        _club(club_id="CORES-VAZIO", colors=[]),
        club_without_colors,
        _club(club_id="CORES-STRING", colors="azul"),
        _club(club_id="CORES-OBJETO", colors={"principal": "azul"}),
        _club(club_id="CORES-ITENS-INVALIDOS", colors=[1, True, None]),
    ]

    stats, clubs, players = _run_export(
        tmp_path,
        [_json_bytes(club) for club in clubs_to_process],
    )

    assert stats.clubs_written == 5
    assert stats.invalid_records == 0
    assert [club["Cores"] for club in clubs] == ["", "", "", "", ""]
    assert players == []


def test_quebra_de_linha_em_campo_e_escapada_corretamente_no_csv(
    tmp_path: Path,
) -> None:
    club_name = "Clube\nTeste"
    player_name = "Jogador\nTeste"

    _, clubs, players = _run_export(
        tmp_path,
        [
            _json_bytes(
                _club(
                    name=club_name,
                    players=[_player(name=player_name)],
                )
            )
        ],
    )

    assert clubs[0]["Nome"] == club_name
    assert players[0]["Nome"] == player_name

    raw_clubs = (tmp_path / "output" / "clubs.csv").read_text(
        encoding="utf-8"
    )
    raw_players = (tmp_path / "output" / "players.csv").read_text(
        encoding="utf-8"
    )

    assert '"Clube\nTeste"' in raw_clubs
    assert '"Jogador\nTeste"' in raw_players


def test_execucao_completa_pelo_terminal(tmp_path: Path) -> None:
    input_path = tmp_path / "entrada.jsonl"
    output_path = tmp_path / "saida pelo terminal"
    script_path = Path(__file__).with_name("club_batch_processor.py")

    input_path.write_bytes(
        _json_bytes(
            _club(
                club_id="CLI-1",
                players=[_player(player_id="CLI-JOG-1")],
            )
        )
        + b"\n"
    )

    result = subprocess.run(
        [
            sys.executable,
            str(script_path),
            "--input",
            str(input_path),
            "--output",
            str(output_path),
            "--progress-every",
            "0",
            "--max-error-messages",
            "0",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Processamento concluído:" in result.stdout
    assert result.stderr == ""
    assert (output_path / "clubs.csv").is_file()
    assert (output_path / "players.csv").is_file()

    with (output_path / "clubs.csv").open(
        encoding="utf-8",
        newline="",
    ) as clubs_file:
        clubs = list(csv.DictReader(clubs_file))

    with (output_path / "players.csv").open(
        encoding="utf-8",
        newline="",
    ) as players_file:
        players = list(csv.DictReader(players_file))

    assert [club["Id do Clube"] for club in clubs] == ["CLI-1"]
    assert [player["Id do Jogador"] for player in players] == ["CLI-JOG-1"]


def test_ordem_dos_cabecalhos_e_exatamente_a_exigida(
    tmp_path: Path,
) -> None:
    _run_export(
        tmp_path,
        [_json_bytes(_club(players=[_player()]))],
    )

    with (tmp_path / "output" / "clubs.csv").open(
        encoding="utf-8",
        newline="",
    ) as clubs_file:
        clubs_header = next(csv.reader(clubs_file))

    with (tmp_path / "output" / "players.csv").open(
        encoding="utf-8",
        newline="",
    ) as players_file:
        players_header = next(csv.reader(players_file))

    assert clubs_header == [
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
    assert players_header == [
        "Id do Clube",
        "Id do Jogador",
        "Nome",
        "Idade",
        "Gols",
        "Data de Estreia",
        "Posição",
        "Número da Camisa",
    ]

