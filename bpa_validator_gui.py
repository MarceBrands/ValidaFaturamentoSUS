#!/usr/bin/env python
"""Small desktop UI for the BPA validator."""

from __future__ import annotations

import csv
import json
import tkinter as tk
from dataclasses import asdict
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from bpa_validator import ValidationReport, validate_bpa


APP_TITLE = "Validador BPA"


class BpaValidatorApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("980x640")
        self.minsize(820, 520)

        self.selected_file = tk.StringVar()
        self.status_text = tk.StringVar(value="Selecione um arquivo BPA para validar.")
        self.summary_text = tk.StringVar(value="")
        self.compact_repeats = tk.BooleanVar(value=True)
        self.warn_procedure_documents = tk.BooleanVar(value=False)
        self.report: ValidationReport | None = None

        self._build_styles()
        self._build_layout()

    def _build_styles(self) -> None:
        style = ttk.Style(self)
        style.configure("Title.TLabel", font=("Segoe UI", 16, "bold"))
        style.configure("Status.TLabel", font=("Segoe UI", 12, "bold"))
        style.configure("Toolbar.TButton", padding=(12, 7))
        style.configure("Summary.TLabel", font=("Segoe UI", 10))

    def _build_layout(self) -> None:
        root = ttk.Frame(self, padding=18)
        root.pack(fill=tk.BOTH, expand=True)

        header = ttk.Frame(root)
        header.pack(fill=tk.X)

        ttk.Label(header, text=APP_TITLE, style="Title.TLabel").pack(side=tk.LEFT)
        ttk.Label(header, textvariable=self.status_text, style="Status.TLabel").pack(side=tk.RIGHT)

        chooser = ttk.Frame(root)
        chooser.pack(fill=tk.X, pady=(18, 10))

        path_entry = ttk.Entry(chooser, textvariable=self.selected_file)
        path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        ttk.Button(chooser, text="Escolher arquivo", command=self.choose_file, style="Toolbar.TButton").pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(chooser, text="Validar", command=self.validate_selected, style="Toolbar.TButton").pack(side=tk.LEFT, padx=(8, 0))

        actions = ttk.Frame(root)
        actions.pack(fill=tk.X, pady=(0, 12))

        ttk.Button(actions, text="Abrir amostra", command=self.open_sample).pack(side=tk.LEFT)
        ttk.Button(actions, text="Salvar JSON", command=self.save_json).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(actions, text="Salvar CSV de erros", command=self.save_csv).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(actions, text="Limpar", command=self.clear).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Checkbutton(actions, text="Agrupar repetidos", variable=self.compact_repeats, command=self._render_report).pack(side=tk.LEFT, padx=(16, 0))
        ttk.Checkbutton(
            actions,
            text="CPF/CNS por procedimento BPA-I (aviso)",
            variable=self.warn_procedure_documents,
            command=self.revalidate_if_file_selected,
        ).pack(side=tk.LEFT, padx=(12, 0))

        ttk.Label(root, textvariable=self.summary_text, style="Summary.TLabel").pack(anchor=tk.W, pady=(0, 8))

        table_frame = ttk.Frame(root)
        table_frame.pack(fill=tk.BOTH, expand=True)

        columns = ("severity", "count", "lines", "folha", "seq", "procedimento", "patient_cns", "patient_cpf", "patient_name", "field", "code", "message", "value")
        self.table = ttk.Treeview(table_frame, columns=columns, show="headings")
        self.table.heading("severity", text="Tipo")
        self.table.heading("count", text="Qtd")
        self.table.heading("lines", text="Linhas")
        self.table.heading("folha", text="Folha")
        self.table.heading("seq", text="Seq")
        self.table.heading("procedimento", text="Procedimento")
        self.table.heading("patient_cns", text="CNS")
        self.table.heading("patient_cpf", text="CPF")
        self.table.heading("patient_name", text="Paciente")
        self.table.heading("field", text="Campo")
        self.table.heading("code", text="Codigo")
        self.table.heading("message", text="Mensagem")
        self.table.heading("value", text="Valor")

        self.table.column("severity", width=90, stretch=False)
        self.table.column("count", width=55, stretch=False)
        self.table.column("lines", width=110, stretch=False)
        self.table.column("folha", width=60, stretch=False)
        self.table.column("seq", width=50, stretch=False)
        self.table.column("procedimento", width=105, stretch=False)
        self.table.column("patient_cns", width=130, stretch=False)
        self.table.column("patient_cpf", width=110, stretch=False)
        self.table.column("patient_name", width=210, stretch=False)
        self.table.column("field", width=150, stretch=False)
        self.table.column("code", width=170, stretch=False)
        self.table.column("message", width=360)
        self.table.column("value", width=180)

        y_scroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.table.yview)
        x_scroll = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL, command=self.table.xview)
        self.table.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)

        self.table.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        self.table.tag_configure("error", foreground="#b42318")
        self.table.tag_configure("warning", foreground="#8a5a00")

        footer = ttk.Label(
            root,
            text="Erros bloqueiam o arquivo. Avisos indicam pontos para conferir antes de enviar ao DATASUS.",
            foreground="#555555",
        )
        footer.pack(anchor=tk.W, pady=(10, 0))

    def choose_file(self) -> None:
        file_path = filedialog.askopenfilename(
            title="Escolha o arquivo BPA",
            filetypes=[
                ("Arquivos BPA", "*.txt *.TXT *.jan *.JAN *.fev *.FEV *.mar *.MAR *.abr *.ABR *.mai *.MAI *.jun *.JUN *.jul *.JUL *.ago *.AGO *.set *.SET *.out *.OUT *.nov *.NOV *.dez *.DEZ"),
                ("Arquivos por competencia", "*.jan *.JAN *.fev *.FEV *.mar *.MAR *.abr *.ABR *.mai *.MAI *.jun *.JUN *.jul *.JUL *.ago *.AGO *.set *.SET *.out *.OUT *.nov *.NOV *.dez *.DEZ"),
                ("Arquivos texto", "*.txt *.TXT"),
                ("Todos os arquivos", "*.*"),
            ],
        )
        if file_path:
            self.selected_file.set(file_path)

    def open_sample(self) -> None:
        sample = Path(__file__).with_name("sample_valid_bpa.txt")
        self.selected_file.set(str(sample))
        self.validate_selected()

    def validate_selected(self) -> None:
        selected = self.selected_file.get().strip('" ')
        if not selected:
            messagebox.showinfo(APP_TITLE, "Escolha um arquivo BPA primeiro.")
            return
        file_path = Path(selected)
        if not file_path.exists():
            messagebox.showerror(APP_TITLE, "Arquivo nao encontrado.")
            return
        if not file_path.is_file():
            messagebox.showerror(APP_TITLE, "Selecione um arquivo BPA, nao uma pasta.")
            return

        try:
            document_mode = "warning" if self.warn_procedure_documents.get() else "off"
            self.report = validate_bpa(file_path, procedure_document_mode=document_mode)
        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"Nao foi possivel validar o arquivo:\n{exc}")
            return

        self._render_report()

    def revalidate_if_file_selected(self) -> None:
        if self.selected_file.get().strip('" '):
            self.validate_selected()

    def _render_report(self) -> None:
        if self.report is None:
            return

        self.table.delete(*self.table.get_children())
        rows = self._display_rows()
        for row in rows:
            self.table.insert(
                "",
                tk.END,
                values=(
                    row["severity"].upper(),
                    row["count"],
                    row["lines"],
                    row["folha"],
                    row["sequencia"],
                    row["procedimento"],
                    row["patient_cns"],
                    row["patient_cpf"],
                    row["patient_name"],
                    row["field"],
                    row["code"],
                    row["message"],
                    row["value"],
                ),
                tags=(row["severity"],),
            )

        status = "VALIDO" if self.report.ok else "INVALIDO"
        self.status_text.set(f"{status}: {self.report.errors} erro(s), {self.report.warnings} aviso(s)")
        self.summary_text.set(
            "Registros: "
            f"cabecalho={self.report.counts['header']} | "
            f"BPA-C={self.report.counts['bpac']} | "
            f"BPA-I={self.report.counts['bpai']} | "
            f"desconhecidos={self.report.counts['unknown']} | "
            f"procedimentos ref={self.report.counts.get('procedimentos_ref', 0)} | "
            f"linhas exibidas={len(rows)}"
        )

        if not self.report.issues:
            messagebox.showinfo(APP_TITLE, "Arquivo validado sem erros ou avisos.")

    def _display_rows(self) -> list[dict[str, str]]:
        if self.report is None:
            return []

        if not self.compact_repeats.get():
            return [self._row_from_issue(issue, 1, [] if issue.line is None else [issue.line]) for issue in self.report.issues]

        grouped: dict[tuple[str, ...], dict[str, object]] = {}
        for issue in self.report.issues:
            if issue.code == "064_065_CPF_PROCEDIMENTO":
                key = (
                    issue.severity,
                    issue.code,
                    issue.field or "",
                    issue.folha or "",
                    issue.procedimento or "",
                    issue.message,
                )
            else:
                key = (
                    issue.severity,
                    issue.code,
                    issue.field or "",
                    issue.value or "",
                    issue.message,
                    str(issue.line or ""),
                )

            item = grouped.setdefault(key, {"issue": issue, "lines": [], "count": 0})
            item["count"] = int(item["count"]) + 1
            if issue.line is not None:
                item["lines"].append(issue.line)

        rows = []
        for item in grouped.values():
            issue = item["issue"]
            lines = item["lines"]
            rows.append(self._row_from_issue(issue, int(item["count"]), lines))
        return rows

    def _row_from_issue(self, issue, count: int, lines: list[int]) -> dict[str, str]:
        if not lines:
            line_text = "" if issue.line is None else str(issue.line)
        elif len(lines) <= 6:
            line_text = ", ".join(str(line) for line in lines)
        else:
            first = ", ".join(str(line) for line in lines[:5])
            line_text = f"{first}... (+{len(lines) - 5})"

        return {
            "severity": issue.severity,
            "count": str(count),
            "lines": line_text,
            "folha": issue.folha or "",
            "sequencia": issue.sequencia or "",
            "procedimento": issue.procedimento or "",
            "patient_cns": "" if count > 1 and issue.code == "064_065_CPF_PROCEDIMENTO" else issue.patient_cns or "",
            "patient_cpf": "" if count > 1 and issue.code == "064_065_CPF_PROCEDIMENTO" else issue.patient_cpf or "",
            "patient_name": "Varios pacientes" if count > 1 and issue.code == "064_065_CPF_PROCEDIMENTO" else issue.patient_name or "",
            "field": issue.field or "",
            "code": issue.code,
            "message": issue.message,
            "value": issue.value or "",
        }

    def save_json(self) -> None:
        if self.report is None:
            messagebox.showinfo(APP_TITLE, "Valide um arquivo antes de salvar.")
            return

        file_path = filedialog.asksaveasfilename(
            title="Salvar relatorio JSON",
            defaultextension=".json",
            filetypes=[("JSON", "*.json")],
        )
        if not file_path:
            return
        Path(file_path).write_text(json.dumps(asdict(self.report), ensure_ascii=False, indent=2), encoding="utf-8")
        messagebox.showinfo(APP_TITLE, "Relatorio JSON salvo.")

    def save_csv(self) -> None:
        if self.report is None:
            messagebox.showinfo(APP_TITLE, "Valide um arquivo antes de salvar.")
            return

        file_path = filedialog.asksaveasfilename(
            title="Salvar CSV de erros",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
        )
        if not file_path:
            return

        with Path(file_path).open("w", newline="", encoding="utf-8-sig") as csv_file:
            writer = csv.writer(csv_file, delimiter=";")
            writer.writerow(["tipo", "qtd", "linhas", "folha", "seq", "procedimento", "cns", "cpf", "paciente", "campo", "codigo", "mensagem", "valor"])
            for row in self._display_rows():
                writer.writerow([
                    row["severity"],
                    row["count"],
                    row["lines"],
                    row["folha"],
                    row["sequencia"],
                    row["procedimento"],
                    row["patient_cns"],
                    row["patient_cpf"],
                    row["patient_name"],
                    row["field"],
                    row["code"],
                    row["message"],
                    row["value"],
                ])
        messagebox.showinfo(APP_TITLE, "CSV de erros salvo.")

    def clear(self) -> None:
        self.report = None
        self.selected_file.set("")
        self.status_text.set("Selecione um arquivo BPA para validar.")
        self.summary_text.set("")
        self.table.delete(*self.table.get_children())


def main() -> None:
    app = BpaValidatorApp()
    app.mainloop()


if __name__ == "__main__":
    main()
