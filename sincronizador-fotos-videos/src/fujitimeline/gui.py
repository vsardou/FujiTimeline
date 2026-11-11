"""Native Windows/macOS desktop UI. Run with python -m fujitimeline.gui."""
from datetime import datetime
from fractions import Fraction
from pathlib import Path
from queue import Queue, Empty
from threading import Thread, Event
import os
import subprocess
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from .calibration import load_profile, save_profile
from .desktop import Request, Session, thumbnail, find_tool, manual_profile, seconds
from .jobs import Cancelled, check_cancel
from . import preferences


class App:
    def __init__(self, root):
        self.root = root
        root.title('FujiTimeline • Fotos e vídeos em sincronia')
        if sys.platform == 'win32':
            icon = Path(__file__).parent / 'assets' / 'fujitimeline.ico'
            if icon.exists():
                root.iconbitmap(str(icon))
        window_height = min(850, root.winfo_screenheight() - 90)
        root.geometry(f'1080x{window_height}+{max(0, (root.winfo_screenwidth() - 1080) // 2)}+30')
        root.minsize(900, 580)
        self.videos = []
        self.visible_videos = []
        self.last_dir = str(Path.home() / 'Pictures')
        self.preferences = preferences.load()
        self.last_dir = self.preferences.get('last_dir', self.last_dir)
        self.session = Session()
        self.cancel_event = Event()
        self.thumb_cancel = Event()
        self.unchecked = set()
        self.review = None
        self.revision = 0
        self.pending = False
        self.debounce = None
        self.exporting = False
        self.closing = False
        self.page = 0
        self.thumb_generation = 0
        self.images = {}
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
        style.configure('Treeview', rowheight=58)
        canvas = tk.Canvas(root, highlightthickness=0)
        scrollbar = ttk.Scrollbar(root, orient='vertical', command=canvas.yview)
        scrollbar.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)
        canvas.configure(yscrollcommand=scrollbar.set)
        body = ttk.Frame(canvas, padding=20)
        content = canvas.create_window((0, 0), window=body, anchor='nw')
        body.bind('<Configure>', lambda _: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda event: canvas.itemconfigure(content, width=event.width))
        def scroll(event):
            if event.widget.winfo_class() not in {'Text', 'Listbox', 'TCombobox', 'Treeview'}:
                delta = -int(event.delta / 120) if abs(event.delta) >= 120 else (-1 if event.delta > 0 else 1)
                canvas.yview_scroll(delta, 'units')
        root.bind('<MouseWheel>', scroll)
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
        self.path_row(media, 'photos', 'Pasta de fotos JPEG', self.preferences.get('photos', ''), 'folder')
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
        default = Path(self.preferences.get('output_dir', str(Path.cwd() / 'output'))) / ('FujiTimeline-' + datetime.now().strftime('%Y%m%d-%H%M%S') + '.fcpxml')
        self.path_row(destination, 'output', '3  •  Salvar timeline em', str(default), 'output')
        actions = ttk.Frame(body)
        actions.pack(fill='x', pady=8)
        self.preview_button = ttk.Button(actions, text='Analisar e ver horários', command=lambda: self.start(False))
        self.preview_button.pack(side='left')
        self.export_button = ttk.Button(actions, text='Gerar FCPXML', style='Accent.TButton', command=lambda: self.start(True))
        self.export_button.pack(side='left', padx=8)
        self.cancel_button = ttk.Button(actions, text='Cancelar', command=self.cancel, state='disabled')
        self.cancel_button.pack(side='left', padx=(0, 8))
        self.open_button = ttk.Button(actions, text='Abrir pasta do resultado', command=self.open_output, state='disabled')
        self.open_button.pack(side='left')
        self.progress = ttk.Progressbar(actions, mode='determinate', length=100)
        self.progress.pack(side='right')
        self.status = ttk.Label(body, text='Selecione vídeos e uma pasta de fotos para começar.')
        self.status.pack(anchor='w', pady=(0, 5))
        review_bar = ttk.Frame(body)
        review_bar.pack(fill='x', pady=4)
        ttk.Label(review_bar, text='Buscar fotos:').pack(side='left')
        ttk.Entry(review_bar, textvariable=self.var('photo_search', ''), width=18).pack(side='left', padx=5)
        self.only_matches = tk.BooleanVar(value=True)
        ttk.Checkbutton(review_bar, text='Só nos períodos dos vídeos', variable=self.only_matches,
                        command=self.filter_photos).pack(side='left')
        ttk.Button(review_bar, text='Marcar filtradas', command=lambda: self.mark(True)).pack(side='left', padx=4)
        ttk.Button(review_bar, text='Desmarcar filtradas', command=lambda: self.mark(False)).pack(side='left')
        ttk.Button(review_bar, text='‹', command=lambda: self.change_page(-1)).pack(side='left', padx=4)
        ttk.Button(review_bar, text='›', command=lambda: self.change_page(1)).pack(side='left')
        self.page_label = ttk.Label(review_bar, text='')
        self.page_label.pack(side='left')
        table_frame = ttk.Frame(body)
        table_frame.pack(fill='both', expand=True)
        columns = ('checked', 'file', 'original', 'corrected', 'video', 'position', 'status')
        self.table = ttk.Treeview(table_frame, columns=columns, show='tree headings', height=4)
        self.table.heading('#0', text='Prévia')
        self.table.column('#0', width=85, stretch=False)
        for col, title, width in zip(columns, ['Usar', 'Foto', 'Original', 'Corrigido', 'Vídeo', 'Posição vídeo / timeline (s)', 'Estado'], [50, 140, 205, 205, 140, 180, 110]):
            self.table.heading(col, text=title)
            self.table.column(col, width=width, minwidth=60)
        self.table.pack(side='top', fill='both', expand=True)
        horizontal = ttk.Scrollbar(table_frame, orient='horizontal', command=self.table.xview)
        horizontal.pack(fill='x')
        self.table.configure(xscrollcommand=horizontal.set)
        self.table.bind('<ButtonRelease-1>', self.toggle_photo)
        self.table.bind('<space>', self.toggle_photo_key)
        self.notes = tk.Text(body, height=3, wrap='word', font=('Segoe UI', 9), state='disabled')
        self.notes.pack(fill='x', pady=(5, 0))
        for key in ('photos', 'offset', 'pair', 'mode', 'fixed', 'tolerance', 'fps', 'sound', 'timezone', 'ffprobe', 'exiftool'):
            self.vars[key].trace_add('write', self.changed)
        self.recursive.trace_add('write', self.changed)
        self.vars['photo_search'].trace_add('write', lambda *_: self.filter_photos())
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
        self.changed()

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
        self.changed()

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

    def remember(self):
        try:
            preferences.save({'last_dir': self.last_dir, 'photos': self.vars['photos'].get(),
                              'output_dir': str(Path(self.vars['output'].get()).parent)})
        except OSError as exc:
            self.status.configure(text=f'Preferências não salvas: {exc}')

    def changed(self, *_):
        self.revision += 1
        if self.debounce:
            self.root.after_cancel(self.debounce)
        if self.busy:
            self.pending = True
            if not self.exporting:
                self.cancel_event.set()
        self.debounce = self.root.after(450, self.auto_start)

    def auto_start(self):
        self.debounce = None
        if self.busy:
            self.pending = True
        elif self.videos and self.vars['photos'].get().strip():
            self.start(False, automatic=True)

    def start(self, export, automatic=False):
        if self.busy:
            return
        if self.debounce:
            self.root.after_cancel(self.debounce)
            self.debounce = None
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
                ffprobe=v['ffprobe'], exiftool=v['exiftool'], unchecked=frozenset(self.unchecked))
        except Exception as exc:
            self.status.configure(text=str(exc))
            if not automatic:
                messagebox.showerror('Confira os campos', str(exc), parent=self.root)
            return
        self.remember()
        self.busy = True
        self.exporting = export
        self.pending = False
        revision = self.revision
        self.cancel_event = Event()
        cancel = self.cancel_event
        self.preview_button.configure(state='disabled')
        self.export_button.configure(state='disabled')
        self.cancel_button.configure(state='normal')
        self.progress.configure(value=0)
        self.status.configure(text='Buscando fotos e lendo metadados…')
        def worker():
            try:
                def progress(done, total, message):
                    self.queue.put(('progress', revision, done, total, message))
                review = self.session.run(request, export, cancel, progress)
                self.queue.put(('done', revision, review, None, request, export, automatic))
            except Exception as exc:
                self.queue.put(('done', revision, None, exc, request, export, automatic))
        Thread(target=worker, daemon=True).start()

    def cancel(self):
        self.pending = False
        if self.debounce:
            self.root.after_cancel(self.debounce)
            self.debounce = None
        self.cancel_event.set()
        self.thumb_cancel.set()
        self.status.configure(text='Cancelando… Se a gravação já começou, XML e relatório serão concluídos.')

    def filtered_photos(self):
        if not self.review:
            return []
        term = self.vars['photo_search'].get().casefold()
        return [t for t in self.review.candidates.photo_timings
                if term in str(t.path).casefold() and (not self.only_matches.get() or t.selected)]

    def filter_photos(self):
        self.page = 0
        self.render_table()

    def change_page(self, delta):
        count = len(self.filtered_photos())
        self.page = max(0, min(max(0, (count - 1) // 40), self.page + delta))
        self.render_table()

    def mark(self, value):
        for photo in self.filtered_photos():
            if photo.selected:
                if value:
                    self.unchecked.discard(photo.path)
                else:
                    self.unchecked.add(photo.path)
        self.render_table()
        self.changed()

    def toggle_photo(self, event):
        if self.table.identify_column(event.x) != '#1':
            return
        self.toggle_item(self.table.identify_row(event.y))

    def toggle_photo_key(self, event):
        self.toggle_item(self.table.focus())
        return 'break'

    def toggle_item(self, item):
        photo = self.row_photos.get(item) if hasattr(self, 'row_photos') else None
        if photo and photo.selected:
            if photo.path in self.unchecked:
                self.unchecked.remove(photo.path)
            else:
                self.unchecked.add(photo.path)
            self.render_table()
            self.changed()

    def render_table(self):
        self.thumb_cancel.set()
        self.thumb_cancel = Event()
        cancel = self.thumb_cancel
        self.thumb_generation += 1
        generation = self.thumb_generation
        self.images.clear()
        self.table.delete(*self.table.get_children())
        self.row_photos = {}
        if not self.review:
            return
        photos = self.filtered_photos()
        self.page = min(self.page, max(0, (len(photos) - 1) // 40))
        subset = photos[self.page * 40:(self.page + 1) * 40]
        candidates = {p.media.path: p for p in self.review.candidates.photos}
        self.page_label.configure(text=f'{self.page + 1}/{max(1, (len(photos) + 39) // 40)} • {len(photos)} fotos')
        jobs = []
        for index, photo in enumerate(subset):
            placed = candidates.get(photo.path)
            used = photo.selected and photo.path not in self.unchecked
            video = self.review.candidates.videos[placed.video_index].media.path.name if placed else '—'
            position = f'{float(placed.source_offset):.3f} / {float(placed.offset):.3f}' if placed else '—'
            state = 'Marcada' if used else ('Desmarcada' if photo.selected else 'Fora do período')
            item = str(index)
            self.table.insert('', 'end', iid=item, text='', values=('☑' if used else '☐', photo.path.name,
                photo.original.raw, photo.corrected_time, video, position, state))
            self.row_photos[item] = photo
            jobs.append((item, photo.path))
        def load_thumbs():
            for item, path in jobs:
                if cancel.is_set():
                    return
                try:
                    picture = thumbnail(path)
                except Exception:
                    picture = None
                self.queue.put(('thumb', generation, item, picture))
        Thread(target=load_thumbs, daemon=True).start()

    def poll(self):
        for _ in range(80):
            try:
                event = self.queue.get_nowait()
            except Empty:
                break
            kind = event[0]
            if kind == 'thumb':
                _, generation, item, picture = event
                if generation == self.thumb_generation and picture is not None and self.table.exists(item):
                    from PIL import ImageTk
                    self.images[item] = ImageTk.PhotoImage(picture, master=self.root)
                    self.table.item(item, image=self.images[item])
            elif kind == 'progress':
                _, revision, done, total, message = event
                if revision == self.revision:
                    self.progress.configure(value=100 * done / max(total, 1))
                    self.status.configure(text=message)
            elif kind == 'done':
                _, revision, review, error, request, exported, automatic = event
                self.busy = False
                self.exporting = False
                self.preview_button.configure(state='normal')
                self.export_button.configure(state='normal')
                self.cancel_button.configure(state='disabled')
                if self.closing:
                    self.remember()
                    self.root.destroy()
                    return
                stale = revision != self.revision
                if error:
                    if not stale:
                        self.status.configure(text=str(error))
                        if not automatic and not isinstance(error, Cancelled):
                            messagebox.showerror('FujiTimeline', str(error), parent=self.root)
                else:
                    plan = review.plan
                    if not stale:
                        self.review = review
                        self.render_table()
                        self.progress.configure(value=100)
                        self.status.configure(text=f'{"Exportado" if exported else "Prévia"}: {len(plan.videos)} vídeo(s) • {len(plan.photos)} marcadas • {len(plan.manually_excluded)} desmarcadas • {len(plan.excluded)} fora do período • {len(plan.skipped_missing_capture_time)} sem data • duração {float(plan.duration):.3f} s • offset {float(request.profile.offset_seconds):+.3f} s')
                        self.notes.configure(state='normal')
                        self.notes.delete('1.0', 'end')
                        self.notes.insert('end', '\n'.join(plan.warnings) or 'Posições por metadados; exportação ajusta à grade de quadros. Clique em Usar ou pressione Espaço para marcar/desmarcar.')
                        self.notes.configure(state='disabled')
                    if exported:
                        self.last_output = request.output.resolve()
                        self.open_button.configure(state='normal')
                        self.notes.configure(state='normal')
                        self.notes.insert('end', f'\nSalvo: {self.last_output}\nRelatório: {self.last_output.with_suffix(".json")}')
                        self.notes.configure(state='disabled')
                if self.pending:
                    self.pending = False
                    self.auto_start()
        self.root.after(75, self.poll)

    def open_output(self):
        if self.last_output:
            folder = str(self.last_output.parent)
            if sys.platform == 'win32':
                os.startfile(folder)
            else:
                subprocess.Popen(['open' if sys.platform == 'darwin' else 'xdg-open', folder])

    def close(self):
        self.thumb_cancel.set()
        if self.busy:
            self.closing = True
            self.cancel()
        else:
            self.remember()
            self.root.destroy()


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == '__main__':
    main()
