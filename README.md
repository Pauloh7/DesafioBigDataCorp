# Introdução Desafio BigDataCorp

Projeto desenvolvido a partir de desafio feito pela empresa BigDataCorp.

# Descrição

Este projeto consiste em uma versão menor de projetos quem consistem em ler um arquivo grande, aplicar regras de negócio e de formatação, e produzir arquivos de saída consistentes.

## 📖 Sumário

1. [Introdução](#introdução-desafio-bigdatacorp)  
2. [Descrição](#descrição)  
3. [Iniciando](#iniciando)  
   - [Requisitos](#requisitos)  
   - [Instalação](#instalação)  
   - [Executando o Projeto](#executando-projeto)  
5. [Executando os Testes](#executando-os-testes)
7. [Autor](#autor)  

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

```cmd
.venv\Scripts\activate.bat
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
## Instalação

### Clonar projeto do git.
* Abrir terminal
* Navegar até a pasta para onde desejar importar o projeto
* Executar o comando
```
git clone git@github.com:Pauloh7/DesafioBigDataCorp.git
```
## Executando Projeto
* Abrir terminal ou powershell
* Navegar até a pasta do projeto
* Executar o comando
```
python club_batch_processor.py --input caminhodoinput\arquivo.jsonl --output pastadosoutputs
```

### Executando os Testes
#### No Windows
* Abrir terminal ou powershell
* Navegar até a pasta do projeto

* Para executar todos os testes do projeto:

```powershell
python -m pytest
```

## Autor
[Paulo Henrique De Souza Gomes](https://www.linkedin.com/in/paulo-henrique-4a849139/)
