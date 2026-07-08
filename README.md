# BPA Validator

Validador inicial em Python para arquivos de exportacao BPA/DATASUS.

Base documental usada:

- `Layout_Exportacao_BPA.pdf`, com layout de cabecalho, BPA-C e BPA-I.
- `BPA_LEIAME.txt`, especialmente alteracoes recentes de CPF/CNS e situacao de rua.

## Uso

### Interface visual

Abra o arquivo:

```powershell
abrir_validador_bpa.bat
```

Na tela, clique em `Escolher arquivo`, selecione o arquivo exportado pelo BPA e clique em `Validar`.

O seletor reconhece arquivos `.txt` e tambem extensoes de competencia: `.jan`, `.fev`, `.mar`, `.abr`, `.mai`, `.jun`, `.jul`, `.ago`, `.set`, `.out`, `.nov` e `.dez`.

Tambem da para abrir direto pelo Python:

```powershell
python bpa_validator_gui.py
```

### Linha de comando

```powershell
python bpa_validator.py C:\caminho\arquivo_bpa.txt
python bpa_validator.py C:\caminho\arquivo_bpa.txt --json
python bpa_validator.py C:\caminho\arquivo_bpa.txt --documentos-procedimento warning
```

Codigo de saida:

- `0`: arquivo sem erros bloqueantes.
- `1`: arquivo invalido.

Na interface e no CSV de erros, as ocorrencias de BPA-I mostram tambem CNS, CPF e nome do paciente quando esses campos existem no arquivo.

## O que esta validando agora

- Identificacao de registros `01`, `02` e `03`.
- Tamanho fixo das linhas: cabecalho 130, BPA-C 48, BPA-I 350 caracteres antes do CRLF.
- BPA-I legado com 328 caracteres, usado antes dos campos CPF e situacao de rua.
- Excedente apos a posicao 328 em BPA-I legado vira aviso, pois o BPA Magnetico costuma aceitar quando o excedente vem de campos finais como e-mail.
- Competencia pela extensao mensal do arquivo, por exemplo `.mai` = maio e `.jun` = junho, comparando com a competencia do cabecalho.
- Tipos numericos e alfabeticos conforme layout.
- Campos obrigatorios estruturais.
- Dominios documentados: destino, origem, sexo, raca/cor e situacao de rua.
- Datas `AAAAMM` e `AAAAMMDD`.
- Faixas de folha, sequencia, idade e quantidade.
- Quantidade de linhas informada no cabecalho.
- Quantidade de folhas, por combinacao tipo/folha.
- Soma de controle do cabecalho.
- Exclusividade entre CPF e CNS do paciente.
- Obrigatoriedade de CPF/CNS por procedimento e competencia fica desligada por padrao. Na interface, marque `CPF/CNS por procedimento BPA-I (aviso)` para conferir como aviso experimental. Arquivos com BPA-C/consolidado nao recebem essa critica.
- Digitos verificadores de CPF, CNS e CNPJ.
- Regra basica de etnia: deve ficar em branco quando raca/cor for diferente de `05`.
- Aviso para situacao de rua antes da competencia `202412`.

## O que fica para a proxima camada

Algumas criticas dependem de tabelas externas e devem entrar como validadores opcionais:

- CNES existente e ativo.
- Procedimento SIGTAP valido por competencia.
- CBO permitido para o procedimento.
- CID permitido/exigido para o procedimento.
- CNS/CPF obrigatorio conforme atributo do procedimento. Esta regra existe na Tabela Unificada/SIGTAP, mas pode divergir do comportamento da importacao BPA; por isso ela nao invalida o arquivo por padrao.
- Servico/classificacao exigidos conforme procedimento.
- Municipio IBGE valido.
- CEP/logradouro e demais cadastros auxiliares.

Por padrao, a referencia de procedimentos e lida de:

```text
C:\Program Files (x86)\Datasus\BPA\S_PA.DBF
```

Na linha de comando, outra pasta de tabelas pode ser informada com:

```powershell
python bpa_validator.py arquivo.jun --sigtap-dir C:\caminho\para\tabelas
```

Use `--documentos-procedimento error` apenas quando quiser tratar essas regras como bloqueantes.

## Caminho recomendado para RAAS e e-SUS

A arquitetura pode virar um pacote com:

- `core`: leitor fixo, relatorio de erros, validadores comuns.
- `bpa`: layout e regras BPA.
- `raas`: layout e regras RAAS.
- `esus`: validacoes e-SUS.
- `refs`: tabelas oficiais carregadas de DBF/CSV/SQLite.
- `cli`: comando unico, por exemplo `sus-validator validate bpa arquivo.txt`.
