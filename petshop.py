import os
import sys
import shutil
import sqlite3
from datetime import datetime
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from PIL import Image, ImageTk, ImageOps

MAX_SERVICOS = 3  # serviço atual + 2 anteriores


def pasta_do_app():
    """Pasta onde fica o .exe (ou o .py). Dados e fotos ficam ao lado dele."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


APP_DIR = pasta_do_app()
DB_PATH = os.path.join(APP_DIR, "dados.db")
FOTOS_DIR = os.path.join(APP_DIR, "fotos")


def hoje_br():
    return datetime.now().strftime("%d/%m/%Y")


def br_para_iso(texto):
    return datetime.strptime(texto.strip(), "%d/%m/%Y").strftime("%Y-%m-%d")


def iso_para_br(texto):
    return datetime.strptime(texto, "%Y-%m-%d").strftime("%d/%m/%Y")


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Cadastro de Cachorros - Petshop")
        self.geometry("1050x720")
        self.minsize(950, 650)

        os.makedirs(FOTOS_DIR, exist_ok=True)
        self.db = sqlite3.connect(DB_PATH)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.criar_tabelas()

        self.dog_id = None            # None = cachorro novo (ainda não salvo)
        self.service_id = None        # None = serviço novo (ainda não salvo)
        self.servicos = []            # linhas dos serviços do cachorro atual
        self.dog_ids_lista = []       # ids mostrados na lista de busca
        self.foto_guardada = None     # caminho relativo da foto já salva
        self.foto_pendente = None     # arquivo escolhido, ainda não copiado
        self.tkimg = None

        self.montar_interface()
        self.buscar()
        self.novo_cachorro()

    # ---------------------------------------------------------------- banco
    def criar_tabelas(self):
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS cachorros (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome_cachorro TEXT NOT NULL,
                nome_dono TEXT,
                endereco TEXT,
                telefone TEXT
            );
            CREATE TABLE IF NOT EXISTS servicos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cachorro_id INTEGER NOT NULL
                    REFERENCES cachorros(id) ON DELETE CASCADE,
                data TEXT NOT NULL,
                observacao TEXT,
                foto TEXT
            );
            """
        )
        self.db.commit()

    # ------------------------------------------------------------ interface
    def montar_interface(self):
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        # ---- coluna esquerda: busca
        esq = ttk.Frame(self, padding=10)
        esq.grid(row=0, column=0, sticky="ns")
        esq.rowconfigure(2, weight=1)

        ttk.Label(esq, text="Pesquisar (cachorro, dono ou telefone):").grid(
            row=0, column=0, sticky="w")
        self.var_busca = tk.StringVar()
        self.var_busca.trace_add("write", lambda *a: self.buscar())
        ttk.Entry(esq, textvariable=self.var_busca, width=34).grid(
            row=1, column=0, sticky="ew", pady=(2, 6))

        self.lista = tk.Listbox(esq, width=38, exportselection=False)
        self.lista.grid(row=2, column=0, sticky="ns")
        self.lista.bind("<<ListboxSelect>>", self.ao_selecionar_cachorro)

        ttk.Button(esq, text="+ Novo cachorro", command=self.novo_cachorro).grid(
            row=3, column=0, sticky="ew", pady=(8, 2))
        ttk.Button(esq, text="Fazer backup", command=self.fazer_backup).grid(
            row=4, column=0, sticky="ew", pady=2)

        # ---- coluna direita
        dir_ = ttk.Frame(self, padding=10)
        dir_.grid(row=0, column=1, sticky="nsew")
        dir_.columnconfigure(0, weight=1)

        # cadastro do cachorro
        cad = ttk.LabelFrame(dir_, text="Cadastro", padding=10)
        cad.grid(row=0, column=0, sticky="ew")
        cad.columnconfigure(1, weight=1)

        self.var_cachorro = tk.StringVar()
        self.var_dono = tk.StringVar()
        self.var_endereco = tk.StringVar()
        self.var_telefone = tk.StringVar()
        campos = [
            ("Nome do cachorro:", self.var_cachorro),
            ("Nome da pessoa:", self.var_dono),
            ("Endereço:", self.var_endereco),
            ("Telefone:", self.var_telefone),
        ]
        for i, (rotulo, var) in enumerate(campos):
            ttk.Label(cad, text=rotulo).grid(row=i, column=0, sticky="w", pady=3)
            ttk.Entry(cad, textvariable=var).grid(
                row=i, column=1, sticky="ew", padx=(8, 0), pady=3)

        botoes = ttk.Frame(cad)
        botoes.grid(row=4, column=0, columnspan=2, sticky="e", pady=(6, 0))
        ttk.Button(botoes, text="Salvar cadastro",
                   command=self.salvar_cadastro).pack(side="left", padx=4)
        ttk.Button(botoes, text="Excluir cachorro",
                   command=self.excluir_cachorro).pack(side="left", padx=4)

        # serviços
        serv = ttk.LabelFrame(
            dir_, text="Serviços (atual + 2 anteriores)", padding=10)
        serv.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        dir_.rowconfigure(1, weight=1)
        serv.columnconfigure(1, weight=1)
        serv.rowconfigure(0, weight=1)

        # lista dos 3 serviços
        lat = ttk.Frame(serv)
        lat.grid(row=0, column=0, sticky="ns", padx=(0, 10))
        self.lista_serv = tk.Listbox(
            lat, width=20, height=3, exportselection=False)
        self.lista_serv.pack(fill="x")
        self.lista_serv.bind("<<ListboxSelect>>", self.ao_selecionar_servico)
        ttk.Button(lat, text="+ Novo serviço",
                   command=self.novo_servico).pack(fill="x", pady=(8, 0))

        # formulário do serviço
        form = ttk.Frame(serv)
        form.grid(row=0, column=1, sticky="nsew")
        form.columnconfigure(1, weight=1)
        form.rowconfigure(1, weight=1)

        ttk.Label(form, text="Data (dd/mm/aaaa):").grid(row=0, column=0, sticky="w")
        self.var_data = tk.StringVar()
        ttk.Entry(form, textvariable=self.var_data, width=14).grid(
            row=0, column=1, sticky="w", padx=8)

        ttk.Label(form, text="Observação:").grid(
            row=1, column=0, sticky="nw", pady=(8, 0))
        self.txt_obs = tk.Text(form, height=8, width=40, wrap="word")
        self.txt_obs.grid(row=1, column=1, sticky="nsew", padx=8, pady=(8, 0))

        # foto
        fotobox = ttk.Frame(form)
        fotobox.grid(row=0, column=2, rowspan=2, padx=(10, 0), sticky="n")
        moldura = tk.Frame(fotobox, width=270, height=270,
                           bg="#e8e8e8", relief="sunken", bd=1)
        moldura.pack()
        moldura.pack_propagate(False)
        self.lbl_foto = tk.Label(moldura, text="(sem foto)", bg="#e8e8e8",
                                 cursor="hand2")
        self.lbl_foto.pack(expand=True)
        self.lbl_foto.bind("<Button-1>", self.abrir_foto_grande)
        ttk.Button(fotobox, text="Escolher foto...",
                   command=self.escolher_foto).pack(fill="x", pady=(6, 0))
        ttk.Button(fotobox, text="Remover foto",
                   command=self.remover_foto).pack(fill="x", pady=(2, 0))
        ttk.Label(fotobox, text="(clique na foto para ampliar)",
                  foreground="gray").pack()

        ttk.Button(serv, text="Salvar serviço",
                   command=self.salvar_servico).grid(
            row=1, column=0, columnspan=2, sticky="e", pady=(10, 0))

    # --------------------------------------------------------------- busca
    def buscar(self):
        termo = f"%{self.var_busca.get().strip()}%"
        linhas = self.db.execute(
            """SELECT id, nome_cachorro, nome_dono FROM cachorros
               WHERE nome_cachorro LIKE ? OR nome_dono LIKE ? OR telefone LIKE ?
               ORDER BY nome_cachorro COLLATE NOCASE""",
            (termo, termo, termo),
        ).fetchall()
        self.lista.delete(0, "end")
        self.dog_ids_lista = []
        for l in linhas:
            dono = f" - {l['nome_dono']}" if l["nome_dono"] else ""
            self.lista.insert("end", f"{l['nome_cachorro']}{dono}")
            self.dog_ids_lista.append(l["id"])
        # mantém o cachorro atual marcado, se aparecer na lista
        if self.dog_id in self.dog_ids_lista:
            idx = self.dog_ids_lista.index(self.dog_id)
            self.lista.selection_set(idx)

    def ao_selecionar_cachorro(self, _evento=None):
        sel = self.lista.curselection()
        if sel:
            self.carregar_cachorro(self.dog_ids_lista[sel[0]])

    # ------------------------------------------------------------ cachorro
    def novo_cachorro(self):
        self.dog_id = None
        self.lista.selection_clear(0, "end")
        for v in (self.var_cachorro, self.var_dono,
                  self.var_endereco, self.var_telefone):
            v.set("")
        self.servicos = []
        self.lista_serv.delete(0, "end")
        self.novo_servico()

    def carregar_cachorro(self, dog_id):
        d = self.db.execute(
            "SELECT * FROM cachorros WHERE id = ?", (dog_id,)).fetchone()
        if not d:
            return
        self.dog_id = dog_id
        self.var_cachorro.set(d["nome_cachorro"])
        self.var_dono.set(d["nome_dono"] or "")
        self.var_endereco.set(d["endereco"] or "")
        self.var_telefone.set(d["telefone"] or "")
        self.carregar_servicos(selecionar_primeiro=True)

    def salvar_cadastro(self):
        nome = self.var_cachorro.get().strip()
        if not nome:
            messagebox.showwarning("Atenção", "Digite o nome do cachorro.")
            return
        dados = (nome, self.var_dono.get().strip(),
                 self.var_endereco.get().strip(),
                 self.var_telefone.get().strip())
        if self.dog_id is None:
            cur = self.db.execute(
                "INSERT INTO cachorros (nome_cachorro, nome_dono, endereco, telefone)"
                " VALUES (?, ?, ?, ?)", dados)
            self.dog_id = cur.lastrowid
        else:
            self.db.execute(
                "UPDATE cachorros SET nome_cachorro=?, nome_dono=?, endereco=?,"
                " telefone=? WHERE id=?", dados + (self.dog_id,))
        self.db.commit()
        self.buscar()
        messagebox.showinfo("Pronto", "Cadastro salvo.")

    def excluir_cachorro(self):
        if self.dog_id is None:
            return
        if not messagebox.askyesno(
                "Excluir",
                "Excluir este cachorro e TODO o histórico e fotos dele?\n"
                "Isso não pode ser desfeito."):
            return
        self.db.execute("DELETE FROM cachorros WHERE id = ?", (self.dog_id,))
        self.db.commit()
        shutil.rmtree(self.pasta_fotos_cachorro(self.dog_id), ignore_errors=True)
        self.buscar()
        self.novo_cachorro()

    # ------------------------------------------------------------ serviços
    def carregar_servicos(self, selecionar_primeiro=False):
        self.servicos = self.db.execute(
            "SELECT * FROM servicos WHERE cachorro_id = ?"
            " ORDER BY data DESC, id DESC", (self.dog_id,)).fetchall()
        self.lista_serv.delete(0, "end")
        for i, s in enumerate(self.servicos):
            sufixo = "  (atual)" if i == 0 else ""
            self.lista_serv.insert("end", iso_para_br(s["data"]) + sufixo)
        if selecionar_primeiro and self.servicos:
            self.lista_serv.selection_set(0)
            self.mostrar_servico(self.servicos[0])
        elif not self.servicos:
            self.novo_servico()

    def ao_selecionar_servico(self, _evento=None):
        sel = self.lista_serv.curselection()
        if sel:
            self.mostrar_servico(self.servicos[sel[0]])

    def mostrar_servico(self, s):
        self.service_id = s["id"]
        self.var_data.set(iso_para_br(s["data"]))
        self.txt_obs.delete("1.0", "end")
        self.txt_obs.insert("1.0", s["observacao"] or "")
        self.foto_guardada = s["foto"]
        self.foto_pendente = None
        self.atualizar_foto()

    def novo_servico(self):
        """Prepara um serviço novo: data de hoje, observação e foto vazias."""
        self.service_id = None
        self.lista_serv.selection_clear(0, "end")
        self.var_data.set(hoje_br())
        self.txt_obs.delete("1.0", "end")
        self.foto_guardada = None
        self.foto_pendente = None
        self.atualizar_foto()

    def salvar_servico(self):
        if self.dog_id is None:
            messagebox.showwarning(
                "Atenção", "Salve o cadastro do cachorro primeiro.")
            return
        try:
            data_iso = br_para_iso(self.var_data.get())
        except ValueError:
            messagebox.showwarning(
                "Data inválida", "Use o formato dd/mm/aaaa (ex.: 16/11/2026).")
            return
        obs = self.txt_obs.get("1.0", "end").strip()

        # copia a foto escolhida para a pasta do cachorro
        foto_final = self.foto_guardada
        foto_antiga_para_apagar = None
        if self.foto_pendente:
            try:
                foto_final = self.copiar_foto(self.foto_pendente, data_iso)
            except Exception as e:
                messagebox.showerror("Erro", f"Não consegui copiar a foto:\n{e}")
                return
            foto_antiga_para_apagar = self.foto_guardada

        if self.service_id is None:
            cur = self.db.execute(
                "INSERT INTO servicos (cachorro_id, data, observacao, foto)"
                " VALUES (?, ?, ?, ?)",
                (self.dog_id, data_iso, obs, foto_final))
            self.service_id = cur.lastrowid
            self.podar_servicos_antigos()
        else:
            self.db.execute(
                "UPDATE servicos SET data=?, observacao=?, foto=? WHERE id=?",
                (data_iso, obs, foto_final, self.service_id))
            self.apagar_arquivo_foto(foto_antiga_para_apagar)
        self.db.commit()

        self.foto_guardada = foto_final
        self.foto_pendente = None
        self.carregar_servicos()
        # reseleciona o serviço salvo (se ainda existir)
        for i, s in enumerate(self.servicos):
            if s["id"] == self.service_id:
                self.lista_serv.selection_set(i)
                break
        messagebox.showinfo("Pronto", "Serviço salvo.")

    def podar_servicos_antigos(self):
        """Mantém só os 3 mais recentes; apaga o resto e as fotos deles."""
        todos = self.db.execute(
            "SELECT id, foto FROM servicos WHERE cachorro_id = ?"
            " ORDER BY data DESC, id DESC", (self.dog_id,)).fetchall()
        for antigo in todos[MAX_SERVICOS:]:
            self.apagar_arquivo_foto(antigo["foto"])
            self.db.execute("DELETE FROM servicos WHERE id = ?", (antigo["id"],))

    # --------------------------------------------------------------- fotos
    def pasta_fotos_cachorro(self, dog_id):
        return os.path.join(FOTOS_DIR, f"{dog_id:04d}")

    def copiar_foto(self, origem, data_iso):
        pasta = self.pasta_fotos_cachorro(self.dog_id)
        os.makedirs(pasta, exist_ok=True)
        ext = os.path.splitext(origem)[1].lower() or ".jpg"
        nome = f"{data_iso}_{datetime.now().strftime('%H%M%S')}{ext}"
        destino = os.path.join(pasta, nome)
        shutil.copy2(origem, destino)
        return f"{self.dog_id:04d}/{nome}"

    def apagar_arquivo_foto(self, rel):
        if not rel:
            return
        try:
            os.remove(os.path.join(FOTOS_DIR, rel))
        except OSError:
            pass

    def caminho_foto_atual(self):
        if self.foto_pendente:
            return self.foto_pendente
        if self.foto_guardada:
            return os.path.join(FOTOS_DIR, self.foto_guardada)
        return None

    def escolher_foto(self):
        inicial = os.path.join(os.path.expanduser("~"), "Downloads")
        if not os.path.isdir(inicial):
            inicial = os.path.expanduser("~")
        arq = filedialog.askopenfilename(
            title="Escolha a foto",
            initialdir=inicial,
            filetypes=[("Imagens", "*.jpg *.jpeg *.png *.bmp *.gif *.webp"),
                       ("Todos os arquivos", "*.*")])
        if arq:
            self.foto_pendente = arq
            self.atualizar_foto()

    def remover_foto(self):
        # a foto antiga só é apagada do disco ao salvar o serviço
        self.foto_pendente = None
        if self.foto_guardada and self.service_id is not None:
            if messagebox.askyesno("Remover foto",
                                   "Remover a foto deste serviço?"):
                self.apagar_arquivo_foto(self.foto_guardada)
                self.db.execute("UPDATE servicos SET foto = NULL WHERE id = ?",
                                (self.service_id,))
                self.db.commit()
                self.foto_guardada = None
        else:
            self.foto_guardada = None
        self.atualizar_foto()

    def atualizar_foto(self):
        caminho = self.caminho_foto_atual()
        if caminho and os.path.exists(caminho):
            try:
                img = Image.open(caminho)
                img = ImageOps.exif_transpose(img)  # corrige foto de celular deitada
                img.thumbnail((260, 260))
                self.tkimg = ImageTk.PhotoImage(img)
                self.lbl_foto.config(image=self.tkimg, text="")
                return
            except Exception:
                pass
        self.tkimg = None
        self.lbl_foto.config(image="", text="(sem foto)")

    def abrir_foto_grande(self, _evento=None):
        caminho = self.caminho_foto_atual()
        if caminho and os.path.exists(caminho) and hasattr(os, "startfile"):
            os.startfile(caminho)

    # -------------------------------------------------------------- backup
    def fazer_backup(self):
        destino = filedialog.askdirectory(
            title="Escolha onde salvar o backup (ex.: pendrive)")
        if not destino:
            return
        nome = "BackupPetshop_" + datetime.now().strftime("%Y-%m-%d_%H%M")
        pasta = os.path.join(destino, nome)
        try:
            os.makedirs(pasta)
            copia = sqlite3.connect(os.path.join(pasta, "dados.db"))
            self.db.backup(copia)
            copia.close()
            if os.path.isdir(FOTOS_DIR):
                shutil.copytree(FOTOS_DIR, os.path.join(pasta, "fotos"))
        except Exception as e:
            messagebox.showerror("Erro no backup", str(e))
            return
        messagebox.showinfo(
            "Backup concluído",
            f"Backup salvo em:\n{pasta}\n\n"
            "Para restaurar: copie o dados.db e a pasta fotos de volta para "
            "a pasta do programa (com o programa fechado).")


if __name__ == "__main__":
    App().mainloop()
