# Introdução Desafio BigDataCorp

Projeto desenvolvido a partir de desafio feito pela empresa BigDataCorp.

# Descrição

Este projeto consiste em uma versão menor de projetos que consistem em ler um grande arquivo, aplicar regras de negócio e de formatação, e produzir arquivos de saída consistentes. O problema se baseia em um arquivo JSONL ( sample_clubes.jsonl , no repositório), onde cada linha é um objeto JSON representando um clube de futebol. Cada clube tem um conjunto de dados próprios e uma lista de jogadores. O programa deve ler esse arquivo e gerar dois arquivos CSV:
1. clubs.csv — um registro por clube (relação 1:1).
2. players.csv — um registro por jogador (relação 1:N a partir da lista dentro de cada
clube).

## Regras de negócio
A saída deve seguir essas regras de negocio
* Filtro por campeonato: gere dados apenas para clubes que disputam a Série A ou a
Série B. Clubes de qualquer outro campeonato não entram em nenhum dos dois arquivos
(nem o clube, nem seus jogadores).

* Ligação 1:N: cada linha de players.csv carrega o club_id do clube a que o jogador
pertence. Um clube sem jogadores não gera nenhuma linha em players.csv , mas
continua aparecendo em clubs.csv (se passar no filtro).

* Colors : a lista de cores deve ser unida em um único campo, separada por | (pipe). Ex.:
["preto", "branco"] → preto|branco . Lista vazia ou ausente → campo vazio.

* Datas: toda data de saída deve estar em yyyy-MM-dd . Se o valor de origem não for uma
data válida, deixe o campo vazio — a linha continua no arquivo normalmente.

* Campos vazios: campos ausentes ou nulos no JSON viram campo vazio no CSV.

* Formato do CSV: arquivos em UTF-8, com linha de cabeçalho, separados por vírgula.
Campos que contenham vírgula, aspas ou quebra de linha devem ser escapados
corretamente (padrão RFC 4180: campo entre aspas duplas, aspas internas duplicadas).

* Robustez: o arquivo de exemplo é limpo, mas a base real com que vamos rodar o seu
código pode conter registros malformados ou incompletos. O programa não deve
abortar por causa de um registro problemático: registros inválidos ficam de fora do
resultado e o processamento segue para os demais.

* Volume de dados: o arquivo de exemplo é pequeno, mas a base real com que vamos
rodar o seu código pode ser muito grande (muitos milhões de registros). Escreva o
programa pensando nesse cenário.

## 📖 Sumário

1. [Introdução](#introdução-desafio-bigdatacorp)  
2. [Descrição](#descrição)  
3. [Iniciando](#iniciando)  
   - [Requisitos](#requisitos)  
   - [Executando o Projeto](#executando-projeto)  
4. [Executando os Testes](#executando-os-testes)
5. [Decisões técnicas](#decisoes-tecnicas)
6. [Autor](#autor)  

# Iniciando

## Requisitos

- Python 3.10 ou superior
- pip
- pytest, apenas para executar os testes

## Instalação do Python

### Windows

1. Baixe e instale o Python pelo site oficial ou pela Microsoft Store.
2. Após a instalação, abra o PowerShell ou o Prompt de Comando.
3. Verifique se o Python foi instalado:

```powershell
python --version
```

Caso o comando `python` não funcione, tente:

```powershell
py --version
```

Verifique também o `pip`:

```powershell
python -m pip --version
```

## Clonar projeto do git.
* Abrir terminal
* Navegar até a pasta para onde desejar importar o projeto
* Executar o comando
```
git clone git@github.com:Pauloh7/DesafioBigDataCorp.git
```

## Criação do ambiente virtual

Dentro da pasta do projeto, execute:

```powershell
python -m venv .venv
```

### Ativação no PowerShell

```powershell
.venv\Scripts\Activate.ps1
```

### Ativação no Prompt de Comando
#### Windows
```cmd
.venv\Scripts\activate.bat
```
#### Linux
```
source .venv/bin/activate
```

Quando o ambiente estiver ativo, o terminal mostrará algo semelhante a:

```text
(.venv) C:\caminho\do\projeto>
```

## Instalação do pytest

Com o ambiente virtual ativo, atualize o `pip`:

```powershell
python -m pip install --upgrade pip
```

Depois, instale o pytest:

```powershell
python -m pip install pytest
```

Confirme a instalação:

```powershell
python -m pytest --version
```
## Desativação do ambiente virtual

Ao terminar, execute:

```powershell
deactivate
```

## Executando Projeto
* Abrir terminal ou powershell
* Navegar até a pasta do projeto
* Executar o comando
```
python club_batch_processor.py --input sample_clubes.jsonl --output resultado
```
Após o processamento, a pasta informada em `--output` conterá:

```text
resultado/
├── clubs.csv
└── players.csv
```
### Parâmetros opcionais

- `--progress-every N`: exibe o progresso a cada N linhas. Use `0` para desativar.
- `--max-error-messages N`: limita a quantidade de erros exibidos individualmente.

### Executando os Testes
#### No Windows
* Abrir terminal ou powershell
* Navegar até a pasta do projeto

* Para executar todos os testes do projeto:

```powershell
python -m pytest
```

## Decisões técnicas

- O JSONL é lido linha por linha para evitar carregar bases grandes na memória.
- A entrada é aberta em modo binário para que uma linha com UTF-8 inválido não interrompa o restante do processamento.
- Os CSVs são inicialmente escritos em arquivos temporários e substituem os arquivos finais somente após o processamento.
- O módulo `csv` é usado para aplicar corretamente o escape de vírgulas, aspas e quebras de linha.
- Mensagens de erro e relatórios de progresso são limitados para evitar excesso de saída em bases grandes.

## Autor
[Paulo Henrique De Souza Gomes](https://www.linkedin.com/in/paulo-henrique-4a849139/)
