"""Native Windows/macOS desktop UI. Run with python -m fujitimeline.gui."""
from datetime import datetime
from fractions import Fraction
from pathlib import Path
from queue import Queue, Empty
from threading import Thread
import os
import subprocess
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from .calibration import load_profile, save_profile
from .desktop import Request, execute, find_tool, manual_profile, seconds


class App:
    def __init__(self, root):
        self.root = root
        root.title('FujiTimeline • Fotos e vídeos em sincronia')
        root.geometry(f'1080x{min(850, root.winfo_screenheight() - 90)}')
        root.minsize(900, 580)
        self.videos = []
        self.visible_videos = []
        self.last_dir = str(Path.home() / 'Pictures')
        self.queue = Queue()
        self.busy = False
        self.loaded_profile = None
        self.last_output = None
        self.vars = {}
        style = ttk.Style(root)
        if 'clam' in style.theme_names():
            style.theme_use('clam')
        style.configure('TLabel', font=('Segoe UI', 10))
        style.configure('TButton', padding=7)
        style.configure('Title.TLabel', font=('Segoe UI', 24, 'bold'))
        style.configure('Accent.TButton', foreground='white', background='#18685c')
        canvas = tk.Canvas(root, highlightthickness=0)
        scrollbar = ttk.Scrollbar(root, orient='vertical', command=canvas.yview)
        scrollbar.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)
        canvas.configure(yscrollcommand=scrollbar.set)
        body = ttk.Frame(canvas, padding=20)
        content = canvas.create_window((0, 0), window=body, anchor='nw')
        body.bind('<Configure>', lambda _: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda event: canvas.itemconfigure(content, width=event.width))
        ttk.Label(body, text='FujiTimeline', style='Title.TLabel').pack(anchor='w')
        ttk.Label(body, text='Suas fotos no instante certo. Mídias originais preservadas.').pack(anchor='w', pady=(0, 12))
        media = ttk.LabelFrame(body, text='1  •  Escolha suas mídias', padding=10)
        media.pack(fill='x')
        bar = ttk.Frame(media)
        bar.pack(fill='x')
        ttk.Button(bar, text='+ Adicionar vídeos…', command=self.add_videos).pack(side='left')
        ttk.Button(bar, text='Remover selecionados', command=self.remove_videos).pack(side='left', padx=6)
        self.video_count = ttk.Label(bar, text='0 vídeos')
        self.video_count.pack(side='left')
        ttk.Label(bar, text='Filtrar lista:').pack(side='left', padx=(20, 4))
        search = self.var('search', '')
        ttk.Entry(bar, textvariable=search, width=24).pack(side='left', fill='x', expand=True)
        search.trace_add('write', lambda *_: self.refresh_videos())
        self.listbox = tk.Listbox(media, height=3, selectmode='extended', exportselection=False)
        self.listbox.pack(fill='x', pady=6)
        self.path_row(media, 'photos', 'Pasta de fotos JPEG', '', 'folder')
        self.path_row(media, 'sound', 'Som de disparo WAV (opcional)', '', 'sound')
        self.recursive = tk.BooleanVar(value=False)
        ttk.Checkbutton(media, text='Incluir subpastas de fotos', variable=self.recursive).pack(anchor='w')

        options = ttk.LabelFrame(body, text='2  •  Ajuste a sincronização', padding=10)
        options.pack(fill='x', pady=10)
        row = ttk.Frame(options)
        row.pack(fill='x')
        self.field(row, 'offset', 'Correção (segundos ou HH:MM:SS)', '0', 18)
        self.field(row, 'pair', 'Nome do par câmera / iPhone', '', 26)
        ttk.Button(row, text='Carregar perfil…', command=self.load).pack(side='left', padx=4, anchor='s')
        ttk.Button(row, text='Salvar perfil…', command=self.save).pack(side='left', anchor='s')
        ttk.Label(options, text='Negativo antecipa a foto; positivo atrasa. Ex.: -2,202. Zero = sem correção. Ajuste manual é experimental.').pack(anchor='w', pady=5)
        row = ttk.Frame(options)
        row.pack(fill='x')
        self.field(row, 'mode', 'Duração das fotos', 'Até a próxima', 18, ['Até a próxima', 'Fixa'])
        self.field(row, 'fixed', 'Duração fixa (s)', '3', 12)
        self.field(row, 'tolerance', 'Tolerância (0–60 s)', '0', 16)
        self.field(row, 'fps', 'FPS da timeline', '30', 16, ['24', '25', '30', '50', '60', '24000/1001', '30000/1001', '60000/1001'])
        self.fixed_entry.configure(state='disabled')
        self.vars['mode'].trace_add('write', lambda *_: self.fixed_entry.configure(
            state='normal' if self.vars['mode'].get() == 'Fixa' else 'disabled'))

        advanced = ttk.Frame(options)
        self.advanced = advanced
        self.show_advanced = tk.BooleanVar(value=False)
        ttk.Checkbutton(options, text='Opções avançadas: fuso e ferramentas', variable=self.show_advanced,
                        command=lambda: advanced.pack(fill='x') if self.show_advanced.get() else advanced.pack_forget()).pack(anchor='w')
        self.path_row(advanced, 'timezone', 'Fuso se ausente no EXIF (opcional)', '', None)
        self.path_row(advanced, 'ffprobe', 'FFprobe', find_tool('ffprobe'), 'tool')
        self.path_row(advanced, 'exiftool', 'ExifTool', find_tool('exiftool'), 'tool')

        destination = ttk.Frame(body)
        destination.pack(fill='x')
        default = Path.cwd() / 'output' / ('FujiTimeline-' + datetime.now().strftime('%Y%m%d-%H%M%S') + '.fcpxml')
        self.path_row(destination, 'output', '3  •  Salvar timeline em', str(default), 'output')
        actions = ttk.Frame(body)
        actions.pack(fill='x', pady=8)
        self.preview_button = ttk.Button(actions, text='Analisar e ver horários', command=lambda: self.start(False))
        self.preview_button.pack(side='left')
        self.export_button = ttk.Button(actions, text='Gerar FCPXML', style='Accent.TButton', command=lambda: self.start(True))
        self.export_button.pack(side='left', padx=8)
        self.open_button = ttk.Button(actions, text='Abrir pasta do resultado', command=self.open_output, state='disabled')
        self.open_button.pack(side='left')
        self.progress = ttk.Progressbar(actions, mode='indeterminate', length=100)
        self.progress.pack(side='right')
        self.status = ttk.Label(body, text='Selecione vídeos e uma pasta de fotos para começar.')
        self.status.pack(anchor='w', pady=(0, 5))
        columns = ('file', 'original', 'corrected', 'position', 'status')
        self.table = ttk.Treeview(body, columns=columns, show='headings', height=5)
        for col, title, width in zip(columns, ['Foto', 'Horário original', 'Horário corrigido', 'Timeline (s)', 'Seleção'], [160, 220, 220, 110, 90]):
            self.table.heading(col, text=title)
            self.table.column(col, width=width, minwidth=60)
        self.table.pack(fill='both', expand=True)
        self.notes = tk.Text(body, height=3, wrap='word', font=('Segoe UI', 9), state='disabled')
        self.notes.pack(fill='x', pady=(5, 0))
        root.after(100, self.poll)
        root.protocol('WM_DELETE_WINDOW', self.close)

    def var(self, key, value):
        self.vars[key] = tk.StringVar(value=value)
        return self.vars[key]

    def field(self, parent, key, label, default, width, values=None):
        frame = ttk.Frame(parent)
        frame.pack(side='left', padx=(0, 12))
        ttk.Label(frame, text=label).pack(anchor='w')
        var = self.var(key, default)
        entry = ttk.Combobox(frame, textvariable=var, values=values, state='readonly', width=width) if values else ttk.Entry(frame, textvariable=var, width=width)
        entry.pack(fill='x')
        if key == 'fixed':
            self.fixed_entry = entry

    def path_row(self, parent, key, label, default, kind):
        row = ttk.Frame(parent)
        row.pack(fill='x', pady=3)
        ttk.Label(row, text=label, width=29).pack(side='left')
        ttk.Entry(row, textvariable=self.var(key, default)).pack(side='left', fill='x', expand=True)
        if kind:
            ttk.Button(row, text='Procurar…', command=lambda: self.browse(key, kind)).pack(side='left', padx=(6, 0))

    def browse(self, key, kind):
        current = Path(self.vars[key].get()).expanduser()
        initial = str(current if current.is_dir() else current.parent) if self.vars[key].get() else self.last_dir
        if kind == 'folder':
            selected = filedialog.askdirectory(parent=self.root, initialdir=initial, title='Escolher pasta de fotografias JPEG')
        elif kind == 'output':
            selected = filedialog.asksaveasfilename(parent=self.root, initialdir=initial, initialfile=current.name,
                defaultextension='.fcpxml', filetypes=[('Final Cut Pro XML', '*.fcpxml')])
        else:
            selected = filedialog.askopenfilename(parent=self.root, initialdir=initial,
                filetypes=[('Áudio WAV', '*.wav')] if kind == 'sound' else [('Executável', '*')])
        if selected:
            self.vars[key].set(selected)
            self.last_dir = str(Path(selected) if kind == 'folder' else Path(selected).parent)

    def add_videos(self):
        paths = filedialog.askopenfilenames(parent=self.root, initialdir=self.last_dir, title='Adicionar um ou mais vídeos',
            filetypes=[('Vídeos', '*.mov *.MOV *.mp4 *.MP4 *.m4v *.M4V'), ('Todos os arquivos', '*')])
        for path in paths:
            item = Path(path).resolve()
            if item not in self.videos:
                self.videos.append(item)
        if paths:
            self.last_dir = str(Path(paths[0]).parent)
            if not self.vars['photos'].get():
                self.vars['photos'].set(self.last_dir)
        self.refresh_videos()

    def refresh_videos(self):
        term = self.vars['search'].get().casefold()
        self.visible_videos = [p for p in self.videos if term in str(p).casefold()]
        self.listbox.delete(0, 'end')
        for path in self.visible_videos:
            self.listbox.insert('end', str(path))
        self.video_count.configure(text=f'{len(self.videos)} vídeos • {len(self.visible_videos)} visíveis')

    def remove_videos(self):
        removed = {self.visible_videos[i] for i in self.listbox.curselection()}
        self.videos = [p for p in self.videos if p not in removed]
        self.refresh_videos()

    def profile(self):
        candidate = manual_profile(self.vars['offset'].get(), self.vars['pair'].get())
        if self.loaded_profile and (candidate.pair_id, candidate.offset_seconds) == (self.loaded_profile.pair_id, self.loaded_profile.offset_seconds):
            return self.loaded_profile
        return candidate

    def load(self):
        path = filedialog.askopenfilename(parent=self.root, filetypes=[('Perfil FujiTimeline', '*.profile.json')])
        if not path:
            return
        try:
            profile = load_profile(Path(path))
            # Decimal display is exact for user-entered offsets; rational profiles keep precision below.
            from decimal import Decimal, localcontext
            with localcontext() as ctx:
                ctx.prec = 40
                value = str(Decimal(profile.offset_seconds.numerator) / Decimal(profile.offset_seconds.denominator))
            if seconds(value) != profile.offset_seconds:
                raise ValueError('Este perfil usa fração não decimal. Utilize-o pela CLI para preservar a precisão.')
            self.vars['offset'].set(value)
            self.vars['pair'].set(profile.pair_id or '')
            self.loaded_profile = profile
            self.status.configure(text=f'Perfil carregado: {profile.name} • {profile.status}')
        except Exception as exc:
            messagebox.showerror('Perfil', str(exc), parent=self.root)

    def save(self):
        try:
            profile = self.profile()
            path = filedialog.asksaveasfilename(parent=self.root, defaultextension='.profile.json', filetypes=[('Perfil FujiTimeline', '*.profile.json')])
            if path:
                save_profile(profile, Path(path))
                self.status.configure(text=f'Perfil salvo: {path}')
        except Exception as exc:
            messagebox.showerror('Perfil', str(exc), parent=self.root)

    def start(self, export):
        if self.busy:
            return
        try:
            v = {key: value.get().strip() for key, value in self.vars.items()}
            if not self.videos or not v['photos']:
                raise ValueError('Adicione pelo menos um vídeo e selecione a pasta de fotos.')
            if export and not v['output']:
                raise ValueError('Escolha o destino do FCPXML.')
            request = Request(tuple(self.videos), Path(v['photos']).expanduser(), self.profile(), Path(v['output']).expanduser(),
                mode='fixed' if v['mode'] == 'Fixa' else 'until_next', fixed=seconds(v['fixed']) if v['mode'] == 'Fixa' else Fraction(3),
                tolerance=seconds(v['tolerance']), fps=Fraction(v['fps']), recursive=self.recursive.get(),
                sound=Path(v['sound']).expanduser() if v['sound'] else None, timezone=v['timezone'] or None,
                ffprobe=v['ffprobe'], exiftool=v['exiftool'])
        except Exception as exc:
            messagebox.showerror('Confira os campos', str(exc), parent=self.root)
            return
        self.busy = True
        self.preview_button.configure(state='disabled')
        self.export_button.configure(state='disabled')
        self.progress.start()
        self.status.configure(text='Lendo metadados… Alterações nos campos valerão na próxima execução.')
        self.table.delete(*self.table.get_children())
        def worker():
            try:
                self.queue.put((execute(request, export), None, request, export))
            except Exception as exc:
                self.queue.put((None, str(exc), request, export))
        Thread(target=worker, daemon=True).start()

    def poll(self):
        try:
            plan, error, request, exported = self.queue.get_nowait()
        except Empty:
            self.root.after(100, self.poll)
            return
        self.busy = False
        self.progress.stop()
        self.preview_button.configure(state='normal')
        self.export_button.configure(state='normal')
        if error:
            self.status.configure(text='Não foi possível concluir. Confira a mensagem.')
            messagebox.showerror('FujiTimeline', error, parent=self.root)
        else:
            positions = {p.media.path: p.offset for p in plan.photos}
            for photo in plan.photo_timings:
                path = photo.path
                self.table.insert('', 'end', values=(path.name, photo.original.raw, photo.corrected_time,
                    f'{float(positions[path]):.3f}' if path in positions else '—', 'Incluída' if path in positions else 'Excluída'))
            self.status.configure(text=f'{"Exportado" if exported else "Prévia por metadados"}: {len(plan.videos)} vídeo(s), {len(plan.photos)} foto(s), {len(plan.excluded)} excluída(s). Correção: {float(request.profile.offset_seconds):+.3f} s.')
            self.notes.configure(state='normal')
            self.notes.delete('1.0', 'end')
            self.notes.insert('end', '\n'.join(plan.warnings) or 'Horários exatos na prévia. A exportação ajusta posições à grade de quadros do projeto.')
            self.notes.configure(state='disabled')
            if exported:
                self.last_output = request.output.resolve()
                self.open_button.configure(state='normal')
                self.notes.configure(state='normal')
                self.notes.insert('end', f'\nSalvo: {self.last_output}\nRelatório: {self.last_output.with_suffix(".json")}')
                self.notes.configure(state='disabled')
        self.root.after(100, self.poll)

    def open_output(self):
        if self.last_output:
            folder = str(self.last_output.parent)
            if sys.platform == 'win32':
                os.startfile(folder)
            else:
                subprocess.Popen(['open' if sys.platform == 'darwin' else 'xdg-open', folder])

    def close(self):
        if self.busy:
            messagebox.showinfo('Processamento em andamento', 'Aguarde a leitura/exportação terminar antes de fechar.', parent=self.root)
        else:
            self.root.destroy()


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == '__main__':
    main()
