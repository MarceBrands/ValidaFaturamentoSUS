#!/usr/bin/env python
"""Validate DATASUS BPA export files.

This validator implements the fixed-width layout documented in
Layout_Exportacao_BPA.pdf from BPA/DATASUS, including the 12/2024 fields.
It intentionally separates structural checks from reference-table checks so
SIGTAP/CNES/IBGE validations can be added without changing the parser.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import struct
from dataclasses import dataclass, asdict
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, Sequence


ALLOWED_RACA = {"01", "02", "03", "04", "05", "99"}
ALLOWED_ORG = {"BPA", "PNI", "SIE", "SIB", "MIN", "PAC", "SCL", "EXT"}
ALLOWED_DST = {"M", "E"}
ALLOWED_SEXO = {"M", "F", "I"}
ALLOWED_SITUACAO_RUA = {"", "N", "S"}
DEFAULT_DATASUS_BPA_DIR = Path(r"C:\Program Files (x86)\Datasus\BPA")
COMPETENCIA_EXTENSIONS = {
    ".jan": "01",
    ".fev": "02",
    ".mar": "03",
    ".abr": "04",
    ".mai": "05",
    ".jun": "06",
    ".jul": "07",
    ".ago": "08",
    ".set": "09",
    ".out": "10",
    ".nov": "11",
    ".dez": "12",
}


@dataclass(frozen=True)
class FieldSpec:
    name: str
    start: int
    end: int
    kind: str = "ALFA"
    required: bool = False
    domain: set[str] | None = None

    @property
    def length(self) -> int:
        return self.end - self.start + 1


@dataclass
class Issue:
    severity: str
    code: str
    message: str
    line: int | None = None
    field: str | None = None
    value: str | None = None
    patient_cns: str | None = None
    patient_cpf: str | None = None
    patient_name: str | None = None
    competencia: str | None = None
    folha: str | None = None
    sequencia: str | None = None
    procedimento: str | None = None


@dataclass
class ValidationReport:
    path: str
    ok: bool
    errors: int
    warnings: int
    header: dict[str, str]
    counts: dict[str, int]
    issues: list[Issue]


@dataclass(frozen=True)
class ProcedureRequirement:
    competencia: str
    procedimento: str
    descricao: str
    cpf_obrigatorio: bool
    cns_obrigatorio: bool


HEADER_FIELDS = [
    FieldSpec("cbc_hdr", 1, 2, "NUM", True, {"01"}),
    FieldSpec("cbc_magic", 3, 7, "ALFA", True, {"#BPA#"}),
    FieldSpec("cbc_mvm", 8, 13, "NUM", True),
    FieldSpec("cbc_lin", 14, 19, "NUM", True),
    FieldSpec("cbc_flh", 20, 25, "NUM", True),
    FieldSpec("cbc_smt_vrf", 26, 29, "NUM", True),
    FieldSpec("cbc_rsp", 30, 59, "ALFA"),
    FieldSpec("cbc_sgl", 60, 65, "ALFA"),
    FieldSpec("cbc_cgccpf", 66, 79, "NUM"),
    FieldSpec("cbc_dst", 80, 119, "ALFA"),
    FieldSpec("cbc_dst_in", 120, 120, "ALFA", True, ALLOWED_DST),
    FieldSpec("cbc_versao", 121, 130, "ALFA"),
]


BPAC_FIELDS = [
    FieldSpec("prd_ident", 1, 2, "NUM", True, {"02"}),
    FieldSpec("prd_cnes", 3, 9, "NUM", True),
    FieldSpec("prd_cmp", 10, 15, "NUM", True),
    FieldSpec("prd_cbo", 16, 21, "ALFA"),
    FieldSpec("prd_flh", 22, 24, "NUM", True),
    FieldSpec("prd_seq", 25, 26, "NUM", True),
    FieldSpec("prd_pa", 27, 36, "NUM", True),
    FieldSpec("prd_idade", 37, 39, "NUM", True),
    FieldSpec("prd_qt", 40, 45, "NUM", True),
    FieldSpec("prd_org", 46, 48, "ALFA", True, ALLOWED_ORG),
]


BPAI_FIELDS = [
    FieldSpec("prd_ident", 1, 2, "NUM", True, {"03"}),
    FieldSpec("prd_cnes", 3, 9, "NUM", True),
    FieldSpec("prd_cmp", 10, 15, "NUM", True),
    FieldSpec("prd_cnsmed", 16, 30, "NUM", True),
    FieldSpec("prd_cbo", 31, 36, "ALFA", True),
    FieldSpec("prd_dtaten", 37, 44, "NUM"),
    FieldSpec("prd_flh", 45, 47, "NUM", True),
    FieldSpec("prd_seq", 48, 49, "NUM", True),
    FieldSpec("prd_pa", 50, 59, "NUM", True),
    FieldSpec("prd_cnspac", 60, 74, "NUM"),
    FieldSpec("prd_sexo", 75, 75, "ALFA", True, ALLOWED_SEXO),
    FieldSpec("prd_ibge", 76, 81, "NUM"),
    FieldSpec("prd_cid", 82, 85, "ALFA"),
    FieldSpec("prd_idade", 86, 88, "NUM", True),
    FieldSpec("prd_qt", 89, 94, "NUM", True),
    FieldSpec("prd_caten", 95, 96, "NUM"),
    FieldSpec("prd_naut", 97, 109, "NUM"),
    FieldSpec("prd_org", 110, 112, "ALFA", True, ALLOWED_ORG),
    FieldSpec("prd_nmpac", 113, 142, "ALFA"),
    FieldSpec("prd_dtnasc", 143, 150, "NUM"),
    FieldSpec("prd_raca", 151, 152, "NUM", True, ALLOWED_RACA),
    FieldSpec("prd_etnia", 153, 156, "NUM"),
    FieldSpec("prd_nac", 157, 159, "NUM"),
    FieldSpec("prd_srv", 160, 162, "NUM"),
    FieldSpec("prd_clf", 163, 165, "NUM"),
    FieldSpec("prd_equipe_seq", 166, 173, "NUM"),
    FieldSpec("prd_equipe_area", 174, 177, "NUM"),
    FieldSpec("prd_cnpj", 178, 191, "NUM"),
    FieldSpec("prd_cep_pcnte", 192, 199, "NUM"),
    FieldSpec("prd_lograd_pcnte", 200, 202, "NUM"),
    FieldSpec("prd_end_pcnte", 203, 232, "ALFA"),
    FieldSpec("prd_compl_pcnte", 233, 242, "ALFA"),
    FieldSpec("prd_num_pcnte", 243, 247, "ALFA"),
    FieldSpec("prd_bairro_pcnte", 248, 277, "ALFA"),
    FieldSpec("prd_ddtel_pcnte", 278, 288, "NUM"),
    FieldSpec("prd_email_pcnte", 289, 328, "ALFA"),
    FieldSpec("prd_ine", 329, 338, "NUM"),
    FieldSpec("prd_cpf_pcnte", 339, 349, "NUM"),
    FieldSpec("prd_situacao_rua", 350, 350, "ALFA", False, ALLOWED_SITUACAO_RUA),
]

BPAI_LEGACY_FIELDS = BPAI_FIELDS[:36]


def slice_fields(line: str, specs: Sequence[FieldSpec]) -> dict[str, str]:
    return {spec.name: line[spec.start - 1 : spec.end] for spec in specs}


def add_issue(
    issues: list[Issue],
    severity: str,
    code: str,
    message: str,
    line: int | None = None,
    field: str | None = None,
    value: str | None = None,
) -> None:
    issues.append(Issue(severity, code, message, line, field, value))


def patient_context(fields: dict[str, str]) -> dict[str, str]:
    return {
        "patient_cns": fields.get("prd_cnspac", "").strip(),
        "patient_cpf": fields.get("prd_cpf_pcnte", "").strip(),
        "patient_name": fields.get("prd_nmpac", "").strip(),
    }


def enrich_issues(issues: list[Issue], start_index: int, fields: dict[str, str]) -> None:
    context = patient_context(fields)
    record_context = {
        "competencia": fields.get("prd_cmp", "").strip(),
        "folha": fields.get("prd_flh", "").strip(),
        "sequencia": fields.get("prd_seq", "").strip(),
        "procedimento": fields.get("prd_pa", "").strip(),
    }
    if not any(context.values()) and not any(record_context.values()):
        return
    for issue in issues[start_index:]:
        if issue.line is None:
            continue
        issue.patient_cns = context["patient_cns"] or None
        issue.patient_cpf = context["patient_cpf"] or None
        issue.patient_name = context["patient_name"] or None
        issue.competencia = record_context["competencia"] or None
        issue.folha = record_context["folha"] or None
        issue.sequencia = record_context["sequencia"] or None
        issue.procedimento = record_context["procedimento"] or None


def is_blank(value: str) -> bool:
    return value.strip() == ""


def is_numeric_value(value: str, required: bool) -> bool:
    if value.isdigit():
        return True
    if not required and value.strip().isdigit():
        return True
    return False


def validate_field(spec: FieldSpec, value: str, line_no: int, issues: list[Issue]) -> None:
    if len(value) != spec.length:
        add_issue(issues, "error", "FIELD_LENGTH", f"O campo {spec.name} esta com tamanho invalido.", line_no, spec.name, value)
        return

    if spec.required and is_blank(value):
        add_issue(issues, "error", "REQUIRED", f"O campo obrigatorio {spec.name} esta em branco.", line_no, spec.name, value)
        return

    if spec.kind == "NUM" and not is_blank(value) and not is_numeric_value(value, spec.required):
        add_issue(issues, "error", "NUMERIC", f"O campo {spec.name} deve conter somente numeros.", line_no, spec.name, value)

    if spec.domain is not None:
        normalized = value.strip()
        if normalized not in spec.domain:
            add_issue(
                issues,
                "error",
                "DOMAIN",
                f"O campo {spec.name} tem valor fora das opcoes permitidas: {sorted(spec.domain)}.",
                line_no,
                spec.name,
                value,
            )


def parse_yyyymm(value: str) -> bool:
    if not re.fullmatch(r"\d{6}", value):
        return False
    year = int(value[:4])
    month = int(value[4:6])
    return 1900 <= year <= 2099 and 1 <= month <= 12


def parse_yyyymmdd(value: str) -> bool:
    if is_blank(value):
        return True
    if not re.fullmatch(r"\d{8}", value):
        return False
    try:
        datetime.strptime(value, "%Y%m%d")
    except ValueError:
        return False
    return True


def valid_cpf(value: str) -> bool:
    cpf = re.sub(r"\D", "", value)
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    nums = [int(d) for d in cpf]
    for digit_index in (9, 10):
        total = sum(nums[i] * ((digit_index + 1) - i) for i in range(digit_index))
        check = (total * 10) % 11
        if check == 10:
            check = 0
        if nums[digit_index] != check:
            return False
    return True


def valid_cns(value: str) -> bool:
    cns = re.sub(r"\D", "", value)
    if len(cns) != 15 or cns == cns[0] * 15:
        return False
    total = sum(int(cns[i]) * (15 - i) for i in range(15))
    return total % 11 == 0


def valid_cnpj(value: str) -> bool:
    cnpj = re.sub(r"\D", "", value)
    if len(cnpj) != 14 or cnpj == cnpj[0] * 14:
        return False
    nums = [int(d) for d in cnpj]
    for size, weights in ((12, [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]), (13, [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])):
        total = sum(nums[i] * weights[i] for i in range(size))
        check = 11 - (total % 11)
        if check >= 10:
            check = 0
        if nums[size] != check:
            return False
    return True


def validate_common(fields: dict[str, str], line_no: int, issues: list[Issue]) -> None:
    if "prd_cmp" in fields and not parse_yyyymm(fields["prd_cmp"]):
        add_issue(issues, "error", "INVALID_COMPETENCIA", "A competencia deve estar no formato AAAAMM e ser uma data valida.", line_no, "prd_cmp", fields["prd_cmp"])

    if "prd_flh" in fields and fields["prd_flh"].isdigit():
        flh = int(fields["prd_flh"])
        if not 1 <= flh <= 999:
            add_issue(issues, "error", "INVALID_FOLHA", "O numero da folha deve estar entre 001 e 999.", line_no, "prd_flh", fields["prd_flh"])

    if "prd_seq" in fields and fields["prd_seq"].isdigit():
        seq = int(fields["prd_seq"])
        limit = 20 if fields.get("prd_ident") == "02" else 99
        if not 1 <= seq <= limit:
            add_issue(issues, "error", "INVALID_SEQUENCIA", f"A sequencia deve estar entre 01 e {limit:02d}.", line_no, "prd_seq", fields["prd_seq"])

    if "prd_idade" in fields and fields["prd_idade"].isdigit():
        age = int(fields["prd_idade"])
        if not 0 <= age <= 130:
            add_issue(issues, "error", "INVALID_IDADE", "A idade deve estar entre 0 e 130 anos.", line_no, "prd_idade", fields["prd_idade"])

    if "prd_qt" in fields and fields["prd_qt"].isdigit() and int(fields["prd_qt"]) <= 0:
        add_issue(issues, "error", "INVALID_QUANTIDADE", "A quantidade deve ser maior que zero.", line_no, "prd_qt", fields["prd_qt"])


def validate_bpai(fields: dict[str, str], line_no: int, issues: list[Issue], legacy: bool = False) -> None:
    for date_field in ("prd_dtaten", "prd_dtnasc"):
        if not parse_yyyymmdd(fields[date_field]):
            add_issue(issues, "error", "INVALID_DATE", f"O campo {date_field} deve estar no formato AAAAMMDD e ser uma data valida.", line_no, date_field, fields[date_field])

    cns_prof = fields["prd_cnsmed"]
    if not is_blank(cns_prof) and cns_prof.isdigit() and not valid_cns(cns_prof):
        add_issue(issues, "warning", "CNS_CHECK_DIGIT", "O digito verificador do CNS do profissional parece invalido.", line_no, "prd_cnsmed", cns_prof)

    cns_paciente = fields["prd_cnspac"]
    cpf_paciente = fields.get("prd_cpf_pcnte", "")
    has_cns = not is_blank(cns_paciente)
    has_cpf = not is_blank(cpf_paciente)

    if has_cns and has_cpf:
        add_issue(issues, "error", "CPF_CNS_EXCLUSIVE", "O paciente deve ser identificado por apenas um documento: CPF ou CNS, nunca os dois.", line_no)
    if has_cns and cns_paciente.isdigit() and not valid_cns(cns_paciente):
        add_issue(issues, "warning", "CNS_CHECK_DIGIT", "O digito verificador do CNS do paciente parece invalido.", line_no, "prd_cnspac", cns_paciente)
    if has_cpf and cpf_paciente.isdigit() and not valid_cpf(cpf_paciente):
        add_issue(issues, "error", "CPF_CHECK_DIGIT", "O digito verificador do CPF do paciente e invalido.", line_no, "prd_cpf_pcnte", cpf_paciente)

    cnpj = fields["prd_cnpj"]
    if not is_blank(cnpj) and cnpj.isdigit() and not valid_cnpj(cnpj):
        add_issue(issues, "warning", "CNPJ_CHECK_DIGIT", "O digito verificador do CNPJ parece invalido.", line_no, "prd_cnpj", cnpj)

    email = fields["prd_email_pcnte"].strip()
    if email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        add_issue(issues, "warning", "EMAIL_FORMAT", "O e-mail do paciente nao parece valido.", line_no, "prd_email_pcnte", email)

    raca = fields["prd_raca"]
    etnia = fields["prd_etnia"]
    if raca != "05" and not is_blank(etnia):
        add_issue(issues, "warning", "ETNIA_WITHOUT_RACA_INDIGENA", "O campo etnia deve ficar em branco quando raca/cor for diferente de 05 - Indigena.", line_no, "prd_etnia", etnia)

    if legacy:
        return

    situacao_rua = fields["prd_situacao_rua"].strip()
    competencia = fields["prd_cmp"]
    if situacao_rua and parse_yyyymm(competencia) and competencia < "202412":
        add_issue(issues, "warning", "SITUACAO_RUA_COMPETENCIA", "O campo situacao de rua e documentado como valido a partir da competencia 202412.", line_no, "prd_situacao_rua", situacao_rua)


def validate_procedure_documents(
    fields: dict[str, str],
    line_no: int,
    issues: list[Issue],
    requirements: dict[tuple[str, str], ProcedureRequirement],
    severity: str,
) -> None:
    if fields.get("prd_ident") != "03" or not requirements:
        return

    competencia = fields.get("prd_cmp", "")
    procedimento = fields.get("prd_pa", "")
    requirement = requirements.get((competencia, procedimento))
    if requirement is None:
        return

    cns_paciente = fields.get("prd_cnspac", "")
    cpf_paciente = fields.get("prd_cpf_pcnte", "")
    has_cns = not is_blank(cns_paciente)
    has_cpf = not is_blank(cpf_paciente)
    proc_label = f"{procedimento} - {requirement.descricao}".strip(" -")

    if requirement.cpf_obrigatorio:
        if not has_cpf:
            detail = " O arquivo esta em layout legado, sem campo CPF." if "prd_cpf_pcnte" not in fields else ""
            add_issue(
                issues,
                severity,
                "064_065_CPF_PROCEDIMENTO",
                f"064-CPF do paciente e obrigatorio; 065-Procedimento exige CPF. Procedimento {proc_label}, competencia {competencia}.{detail}",
                line_no,
                "prd_cpf_pcnte",
                cpf_paciente,
            )
        elif has_cns:
            add_issue(
                issues,
                severity,
                "CPF_OBRIGATORIO_COM_CNS",
                f"O procedimento {proc_label} exige identificacao por CPF; nao informe CNS neste atendimento.",
                line_no,
                "prd_cnspac",
                cns_paciente,
            )
    elif requirement.cns_obrigatorio and not (has_cns or has_cpf):
        add_issue(
            issues,
            severity,
            "CNS_OU_CPF_OBRIGATORIO_PROCEDIMENTO",
            f"O procedimento {proc_label} exige identificacao do paciente por CNS ou CPF para a competencia {competencia}.",
            line_no,
            "prd_cnspac",
            cns_paciente,
        )


def checksum(records: Iterable[dict[str, str]]) -> int:
    total = 0
    for fields in records:
        pa = fields.get("prd_pa", "")
        qt = fields.get("prd_qt", "")
        if pa.isdigit() and qt.isdigit():
            total += int(pa) + int(qt)
    return 1111 + (total % 1111)


def unique_folhas(records: Iterable[dict[str, str]]) -> int:
    return len({(fields.get("prd_ident", ""), fields.get("prd_flh", "")) for fields in records if fields.get("prd_flh", "").isdigit()})


def read_dbf(path: Path) -> Iterable[dict[str, str]]:
    data = path.read_bytes()
    record_count = struct.unpack("<I", data[4:8])[0]
    header_len = struct.unpack("<H", data[8:10])[0]
    record_len = struct.unpack("<H", data[10:12])[0]
    fields: list[tuple[str, int, int]] = []
    pos = 32
    offset = 1

    while pos < header_len and data[pos] != 0x0D:
        raw = data[pos : pos + 32]
        name = raw[:11].split(b"\x00", 1)[0].decode("latin-1")
        length = raw[16]
        fields.append((name, offset, length))
        offset += length
        pos += 32

    for index in range(record_count):
        record = data[header_len + index * record_len : header_len + (index + 1) * record_len]
        if not record or record[0:1] == b"*":
            continue
        row = {}
        for name, field_offset, length in fields:
            row[name] = record[field_offset : field_offset + length].decode("latin-1", errors="replace").strip()
        yield row


def load_procedure_requirements(sigtap_dir: Path | None = None) -> dict[tuple[str, str], ProcedureRequirement]:
    directory = sigtap_dir or DEFAULT_DATASUS_BPA_DIR
    path = directory / "S_PA.DBF"
    if not path.exists():
        return {}

    requirements: dict[tuple[str, str], ProcedureRequirement] = {}
    for row in read_dbf(path):
        competencia = row.get("PA_CMP", "")
        procedimento = row.get("PA_ID", "") + row.get("PA_DV", "")
        if not competencia or not procedimento:
            continue
        requirements[(competencia, procedimento)] = ProcedureRequirement(
            competencia=competencia,
            procedimento=procedimento,
            descricao=row.get("PA_DC", ""),
            cpf_obrigatorio=row.get("PA_CPFPCN", "").upper() == "S",
            cns_obrigatorio=row.get("PA_CNSPCN", "").upper() == "S",
        )
    return requirements


def competencia_month_from_extension(path: Path) -> str | None:
    return COMPETENCIA_EXTENSIONS.get(path.suffix.lower())


def decode_lines(path: Path, issues: list[Issue]) -> list[str]:
    raw = path.read_bytes()
    if b"\n" in raw and b"\r\n" not in raw:
        add_issue(issues, "warning", "LINE_ENDING", "O arquivo usa quebra de linha LF; o layout DATASUS documenta CRLF.")
    try:
        text = raw.decode("latin-1")
    except UnicodeDecodeError:
        text = raw.decode("latin-1", errors="replace")
        add_issue(issues, "warning", "ENCODING", "O arquivo contem bytes que nao puderam ser decodificados perfeitamente.")
    return text.splitlines()


def validate_bpa(
    path: Path,
    sigtap_dir: Path | None = None,
    procedure_document_mode: str = "off",
) -> ValidationReport:
    issues: list[Issue] = []
    lines = decode_lines(path, issues)
    procedure_document_mode = procedure_document_mode.lower()
    if procedure_document_mode not in {"off", "warning", "error"}:
        raise ValueError("procedure_document_mode deve ser off, warning ou error.")
    has_bpac_records = any(line.startswith("02") for line in lines)
    validate_procedure_documents_enabled = procedure_document_mode != "off" and not has_bpac_records
    requirements = load_procedure_requirements(sigtap_dir) if validate_procedure_documents_enabled else {}
    header: dict[str, str] = {}
    production_records: list[dict[str, str]] = []
    counts = {"header": 0, "bpac": 0, "bpai": 0, "bpai_legacy": 0, "unknown": 0, "procedimentos_ref": len(requirements)}

    if not lines:
        add_issue(issues, "error", "EMPTY_FILE", "O arquivo esta vazio.")
    elif not lines[0].startswith("01"):
        add_issue(issues, "error", "MISSING_HEADER", "A primeira linha deve ser o cabecalho BPA, registro 01.", 1)

    for line_no, line in enumerate(lines, 1):
        ident = line[:2]
        if ident == "01":
            counts["header"] += 1
            if len(line) != 130:
                add_issue(issues, "error", "LINE_LENGTH", "O cabecalho deve ter 130 caracteres antes da quebra de linha.", line_no, value=str(len(line)))
            fields = slice_fields(line.ljust(130), HEADER_FIELDS)
            for spec in HEADER_FIELDS:
                validate_field(spec, fields[spec.name], line_no, issues)
            if not parse_yyyymm(fields["cbc_mvm"]):
                add_issue(issues, "error", "INVALID_MOVIMENTO", "O movimento do cabecalho deve estar no formato AAAAMM e ser uma data valida.", line_no, "cbc_mvm", fields["cbc_mvm"])
            header = fields
        elif ident == "02":
            issue_start = len(issues)
            counts["bpac"] += 1
            if len(line) != 48:
                add_issue(issues, "error", "LINE_LENGTH", "A linha BPA-C deve ter 48 caracteres antes da quebra de linha.", line_no, value=str(len(line)))
            fields = slice_fields(line.ljust(48), BPAC_FIELDS)
            for spec in BPAC_FIELDS:
                validate_field(spec, fields[spec.name], line_no, issues)
            validate_common(fields, line_no, issues)
            enrich_issues(issues, issue_start, fields)
            production_records.append(fields)
        elif ident == "03":
            issue_start = len(issues)
            counts["bpai"] += 1
            legacy = len(line) != 350
            if legacy:
                counts["bpai_legacy"] += 1
            expected_len = 328 if legacy else 350
            specs = BPAI_LEGACY_FIELDS if legacy else BPAI_FIELDS
            if legacy and len(line) < 328:
                add_issue(
                    issues,
                    "warning",
                    "TRAILING_BLANKS_TRIMMED",
                    "A linha BPA-I legada esta menor que 328 caracteres; as posicoes opcionais finais ausentes foram tratadas como brancos.",
                    line_no,
                    value=str(len(line)),
                )
            elif legacy and len(line) > 328:
                extra = line[328:].strip()
                add_issue(
                    issues,
                    "error",
                    "LEGACY_LINE_OVERFLOW",
                    "A linha BPA-I legada passou de 328 caracteres; verifique campos finais como e-mail, que no layout tem limite de 40 caracteres.",
                    line_no,
                    "prd_email_pcnte",
                    extra or str(len(line)),
                )
            elif len(line) not in {328, 350}:
                add_issue(issues, "error", "LINE_LENGTH", "A linha BPA-I deve ter 328 caracteres no layout legado ou 350 no layout atual, antes da quebra de linha.", line_no, value=str(len(line)))
            fields = slice_fields(line.ljust(expected_len), specs)
            for spec in specs:
                validate_field(spec, fields[spec.name], line_no, issues)
            validate_common(fields, line_no, issues)
            validate_bpai(fields, line_no, issues, legacy)
            validate_procedure_documents(fields, line_no, issues, requirements, procedure_document_mode)
            enrich_issues(issues, issue_start, fields)
            production_records.append(fields)
        else:
            counts["unknown"] += 1
            add_issue(issues, "error", "UNKNOWN_RECORD", "Identificador de registro desconhecido.", line_no, value=ident)

    if counts["header"] != 1:
        add_issue(issues, "error", "HEADER_COUNT", "O arquivo deve conter exatamente um cabecalho, registro 01.", None, value=str(counts["header"]))

    if counts["bpai_legacy"]:
        add_issue(
            issues,
            "warning",
            "BPAI_LEGACY_LAYOUT",
            f"O arquivo contem {counts['bpai_legacy']} linha(s) BPA-I no layout legado de 328 caracteres, sem os campos CPF e situacao de rua.",
        )

    if header:
        extension_month = competencia_month_from_extension(path)
        if extension_month and parse_yyyymm(header["cbc_mvm"]) and header["cbc_mvm"][4:6] != extension_month:
            add_issue(
                issues,
                "warning",
                "EXTENSION_COMPETENCIA",
                f"A extensao {path.suffix.lower()} indica mes {extension_month}, mas o cabecalho informa competencia {header['cbc_mvm']}.",
                1,
                "cbc_mvm",
                header["cbc_mvm"],
            )

        expected_lines = counts["bpac"] + counts["bpai"]
        if header["cbc_lin"].isdigit() and int(header["cbc_lin"]) != expected_lines:
            add_issue(issues, "error", "HEADER_LINE_COUNT", "A quantidade de linhas de producao informada no cabecalho nao bate com o arquivo.", 1, "cbc_lin", header["cbc_lin"])

        expected_folhas = unique_folhas(production_records)
        if header["cbc_flh"].isdigit() and int(header["cbc_flh"]) != expected_folhas:
            add_issue(issues, "warning", "HEADER_FOLHA_COUNT", "A quantidade de folhas informada no cabecalho nao bate com as folhas encontradas no arquivo.", 1, "cbc_flh", header["cbc_flh"])

        expected_checksum = checksum(production_records)
        if header["cbc_smt_vrf"].isdigit() and int(header["cbc_smt_vrf"]) != expected_checksum:
            add_issue(issues, "error", "HEADER_CHECKSUM", f"A soma de controle do cabecalho deveria ser {expected_checksum:04d}.", 1, "cbc_smt_vrf", header["cbc_smt_vrf"])

    errors = sum(1 for issue in issues if issue.severity == "error")
    warnings = sum(1 for issue in issues if issue.severity == "warning")
    return ValidationReport(str(path), errors == 0, errors, warnings, header, counts, issues)


def print_text(report: ValidationReport) -> None:
    status = "OK" if report.ok else "INVALIDO"
    print(f"{status}: {report.path}")
    print(f"Registros: cabecalho={report.counts['header']} BPA-C={report.counts['bpac']} BPA-I={report.counts['bpai']} desconhecidos={report.counts['unknown']}")
    if report.counts.get("procedimentos_ref"):
        print(f"Referencia SIGTAP local: {report.counts['procedimentos_ref']} procedimento(s) carregado(s)")
    print(f"Ocorrencias: erros={report.errors} avisos={report.warnings}")
    for issue in report.issues:
        severity = "ERRO" if issue.severity == "error" else "AVISO"
        location = f"linha {issue.line}" if issue.line is not None else "arquivo"
        field = f" campo {issue.field}" if issue.field else ""
        patient = ""
        if issue.patient_name or issue.patient_cns or issue.patient_cpf:
            bits = []
            if issue.patient_name:
                bits.append(f"paciente={issue.patient_name!r}")
            if issue.patient_cns:
                bits.append(f"CNS={issue.patient_cns!r}")
            if issue.patient_cpf:
                bits.append(f"CPF={issue.patient_cpf!r}")
            patient = " " + " ".join(bits)
        value = f" valor={issue.value!r}" if issue.value is not None else ""
        print(f"[{severity}] {issue.code} em {location}{field}{patient}: {issue.message}{value}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Valida arquivos de exportacao BPA/DATASUS em layout posicional.")
    parser.add_argument("arquivo", type=Path, help="Caminho do arquivo BPA exportado.")
    parser.add_argument("--json", action="store_true", help="Mostra o relatorio em JSON.")
    parser.add_argument("--sigtap-dir", type=Path, default=None, help="Pasta com as tabelas locais do BPA/SIGTAP, incluindo S_PA.DBF.")
    parser.add_argument(
        "--documentos-procedimento",
        choices=("off", "warning", "error"),
        default="off",
        help="Valida CPF/CNS obrigatorio por procedimento. Padrao: off, pois a regra depende de atributos SIGTAP e pode divergir da importacao BPA.",
    )
    args = parser.parse_args(argv)

    report = validate_bpa(args.arquivo, args.sigtap_dir, args.documentos_procedimento)
    if args.json:
        print(json.dumps(asdict(report), ensure_ascii=False, indent=2))
    else:
        print_text(report)
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
