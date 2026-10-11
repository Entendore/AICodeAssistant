        if QMessageBox.question(self, "Delete", "Delete this chat?") == QMessageBox.Yes:
            p = CHAT_DIR / f"{sid}.json"
            if p.exists(): p.unlink()
            del self._sessions[sid]
            self.lw.takeItem(r)

    def rename_current(self, name: str):
        if self._current and self._current in self._sessions:
            self._sessions[self._current].title = name
            idx = list(self._sessions.keys()).index(self._current)
            self.lw.item(idx).setText(name)
            self._sessions[self._current]._save()

    def add_session(self, session: ChatSession):
        self._sessions[session.session_id] = session
        self.lw.addItem(session.title)
        self.lw.setCurrentRow(self.lw.count() - 1)

    def _refresh_list(self):
        self.lw.clear()
        for sid, s in self._sessions.items():
            self.lw.addItem(s.title)
        if self._current and self._current in self._sessions:
            idx = list(self._sessions.keys()).index(self._current)
            self.lw.setCurrentRow(idx)

# ═══════════════════════════════════════════════════════════════════════════════
# MESSAGE BUBBLE
# ═══════════════════════════════════════════════════════════════════════════════
class EnhancedMessageBubble(QFrame):
    run_code_requested = Signal(str, str)
    save_file_requested = Signal(str, str)

    def __init__(self, message: Message, parent=None):
        super().__init__(parent)
        self.message = message
        self._code_blocks: List[Tuple[str, str]] = []
        self._streaming_edit: Optional[QTextEdit] = None
        self._actions_bar: Optional[OutputActionsBar] = None
        self._setup_ui()

    def _setup_ui(self):
        is_user = self.message.role == Role.USER
        self.setObjectName("userBubble" if is_user else "assistantBubble")
        self._main_layout = QVBoxLayout(self)
        self._main_layout.setContentsMargins(12, 8, 12, 8)
        self._main_layout.setSpacing(4)

        # Header
        hl = QHBoxLayout()
        icon = "👤" if is_user else "🤖"
        name = "You" if is_user else "Assistant"
        hl.addWidget(QLabel(icon))
        nl = QLabel(name); nl.setObjectName("msgName"); hl.addWidget(nl)

        if self.message.skill and self.message.skill in SKILLS:
            sl = QLabel(f"[{SKILLS[self.message.skill].icon} {SKILLS[self.message.skill].display_name}]")
            sl.setObjectName("skillTag"); hl.addWidget(sl)

        hl.addStretch()
        ts = datetime.fromtimestamp(self.message.timestamp).strftime("%H:%M")
        tl = QLabel(ts); tl.setObjectName("msgTime"); hl.addWidget(tl)
        self._main_layout.addLayout(hl)

        if not self.message.content:
            # Placeholder for streaming
            self._streaming_edit = QTextEdit()
            self._streaming_edit.setReadOnly(True)
            self._streaming_edit.setObjectName("msgText")
            self._streaming_edit.setStyleSheet("background:transparent;border:none;")
            self._streaming_edit.document().setDocumentMargin(0)
            self._main_layout.addWidget(self._streaming_edit)
        else:
            self._render_content()

        if self.message.token_count:
            tc = QLabel(f"~{self.message.token_count} tokens"); tc.setObjectName("tokenCount")
            tc.setAlignment(Qt.AlignRight); self._main_layout.addWidget(tc)

        if not is_user and self._code_blocks and self.message.content:
            self._actions_bar = OutputActionsBar(self._code_blocks)
            self._actions_bar.copy_code.connect(lambda c: QApplication.clipboard().setText(c))
            self._actions_bar.run_code.connect(self.run_code_requested.emit)
            self._actions_bar.save_file.connect(self.save_file_requested.emit)
            self._main_layout.addWidget(self._actions_bar)

        self.setStyleSheet("""
            #userBubble { background:#2a3a4a; border-radius:12px; border:1px solid #3a4a5a; margin-left:40px; }
            #assistantBubble { background:#1e2a36; border-radius:12px; border:1px solid #2a3a4a; margin-right:20px; }
            #msgName { color:#f0f6fc; font-weight:bold; font-size:13px; }
            #msgTime { color:#484f58; font-size:11px; }
            #skillTag { color:#58a6ff; font-size:11px; background:#1a2332; padding:1px 6px; border-radius:3px; }
            #tokenCount { color:#484f58; font-size:10px; }
            #msgText { color:#c9d1d9; font-size:13px; line-height:1.5; }
        """)

    def _render_content(self):
        parts = re.split(r'(```[\s\S]*?```)', self.message.content)
        for part in parts:
            if part.startswith('```') and part.endswith('```'):
                lines = part[3:-3].split('\n', 1)
                lang = lines[0].strip() if lines else ""
                code = lines[1].strip('\n') if len(lines) > 1 else ""
                if code:
                    self._code_blocks.append((lang, code))
                    sec = CollapsibleSection(f"```{lang} ({len(code)} chars)")
                    sec.add_widget(CodeBlockWidget(code, lang)); sec.expand()
                    self._main_layout.addWidget(sec)
            elif part.strip():
                te = QTextEdit(); te.setReadOnly(True); te.setObjectName("msgText")
                te.setHtml(self._md_to_html(part)); te.document().setDocumentMargin(0)
                te.setMaximumHeight(te.document().size().height() + 20)
                te.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
                te.setStyleSheet("background:transparent;border:none;")
                self._main_layout.addWidget(te)

    def append_text(self, text: str):
        if self._streaming_edit:
            cursor = self._streaming_edit.textCursor()
            cursor.movePosition(cursor.End)
            cursor.insertHtml(self._md_to_html(text))
            self._streaming_edit.setMaximumHeight(self._streaming_edit.document().size().height() + 20)

    def finalize_streaming(self, full_content: str):
        if self._streaming_edit:
            self._main_layout.removeWidget(self._streaming_edit)
            self._streaming_edit.deleteLater(); self._streaming_edit = None
        # Remove old actions
        if self._actions_bar:
            self._main_layout.removeWidget(self._actions_bar)
            self._actions_bar.deleteLater(); self._actions_bar = None
        # Remove old rendered content
        while self._main_layout.count() > 1:
            item = self._main_layout.takeAt(self._main_layout.count() - 1)
            if item.widget(): item.widget().deleteLater()
        self._code_blocks.clear()
        self.message.content = full_content
        self._render_content()
        if self.message.role == Role.ASSISTANT and self._code_blocks:
            self._actions_bar = OutputActionsBar(self._code_blocks)
            self._actions_bar.copy_code.connect(lambda c: QApplication.clipboard().setText(c))
            self._actions_bar.run_code.connect(self.run_code_requested.emit)
            self._actions_bar.save_file.connect(self.save_file_requested.emit)
            self._main_layout.addWidget(self._actions_bar)
        if self.message.token_count:
            tc = QLabel(f"~{self.message.token_count} tokens"); tc.setObjectName("tokenCount")
            tc.setAlignment(Qt.AlignRight); self._main_layout.addWidget(tc)

    @staticmethod
    def _md_to_html(text: str) -> str:
        text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        text = re.sub(r'`([^`]+)`', r'<code style="background:#1a2a3a;padding:1px 5px;border-radius:3px;font-family:JetBrains Mono,monospace;font-size:12px;color:#e5c07b;">\1</code>', text)
        text = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', text)
        text = re.sub(r'^### (.+)$', r'<h4 style="color:#61afef;margin:6px 0 2px;">\1</h4>', text, flags=re.M)
        text = re.sub(r'^## (.+)$', r'<h3 style="color:#61afef;margin:8px 0 4px;">\1</h3>', text, flags=re.M)
        text = re.sub(r'^# (.+)$', r'<h2 style="color:#61afef;margin:10px 0 4px;">\1</h2>', text, flags=re.M)
        text = re.sub(r'^- (.+)$', r'<span style="color:#e06c75;">•</span> \1', text, flags=re.M)
        text = text.replace('\n', '<br>')
        return text

# ═══════════════════════════════════════════════════════════════════════════════
# CHAT WIDGET
# ═══════════════════════════════════════════════════════════════════════════════
class ChatWidget(QWidget):
    send_requested = Signal(str, str)
    agent_requested = Signal(str)
    run_code_requested = Signal(str, str)

    def __init__(self, session: ChatSession, backend: LlamaBackend, tools: ToolRegistry,
                 templates: PromptTemplates, branch_mgr: BranchManager,
                 input_history: InputHistoryManager, rag: RAGLiteInjector,
                 plugins: PluginSystem, toast: ToastManager, parent=None):
        super().__init__(parent)
        self.session = session; self.backend = backend; self.tools = tools
        self.templates = templates; self.branch_mgr = branch_mgr
        self.input_history = input_history; self.rag = rag; self.plugins = plugins
        self.toast = toast; self._generating = False; self._stream_buffer = ""
        self._streaming_bubble: Optional[EnhancedMessageBubble] = None
        self._sys_override = ""; self._welcome: Optional[WelcomeWidget] = None
        self._rag_on = True
        self._ui(); self._connect(); self._show_welcome(); self._render_history()

    def _ui(self):
        lay = QVBoxLayout(self); lay.setContentsMargins(0,0,0,0); lay.setSpacing(0)
        # Skill bar
        sb = QFrame(); sb.setObjectName("skillBar"); sb.setFixedHeight(40)
        sbl = QHBoxLayout(sb); sbl.setContentsMargins(8,4,8,4)
        sbl.addWidget(QLabel("Skill:"))
        self.sc = QComboBox(); self.sc.setObjectName("skillCombo")
        for k, s in SKILLS.items(): self.sc.addItem(f"{s.icon} {s.display_name}", k)
        self.sc.setCurrentIndex(list(SKILLS.keys()).index(self.session.current_skill))
        self.sc.setFixedWidth(180); sbl.addWidget(self.sc)
        self.rag_cb = QCheckBox("📂 RAG"); self.rag_cb.setObjectName("agentCheck"); self.rag_cb.setChecked(True)
        self.rag_cb.setToolTip("Auto-attach relevant file context"); sbl.addWidget(self.rag_cb)
        self.sp_btn = QPushButton("📝 Sys"); self.sp_btn.setObjectName("titleBarBtn"); self.sp_btn.setFixedHeight(24)
        self.sp_btn.setToolTip("Override system prompt"); self.sp_btn.clicked.connect(self._override_sys); sbl.addWidget(self.sp_btn)
        sbl.addStretch()
        self.ag_cb = QCheckBox("🤖 Agent"); self.ag_cb.setObjectName("agentCheck"); self.ag_cb.setChecked(self.session.agent_mode)
        sbl.addWidget(self.ag_cb)
        self.ctx_l = QLabel("Context: 0t"); self.ctx_l.setObjectName("contextLabel"); sbl.addWidget(self.ctx_l)
        lay.addWidget(sb)
        # Scroll
        self.scroll = QScrollArea(); self.scroll.setObjectName("chatScroll"); self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.sc_w = QWidget(); self.sc_l = QVBoxLayout(self.sc_w); self.sc_l.setContentsMargins(8,8,8,8); self.sc_l.setSpacing(8)
        self.sc_l.addStretch(); self.scroll.setWidget(self.sc_w); lay.addWidget(self.scroll,1)
        # Input
        inf = QFrame(); inf.setObjectName("inputFrame"); inl = QVBoxLayout(inf); inl.setContentsMargins(8,8,8,8); inl.setSpacing(6)
        self.inp = FileDropTextEdit(); self.inp.setObjectName("chatInput")
        self.inp.setPlaceholderText("Type message... (↑↓ history, Enter send, Shift+Enter newline)\nDrag & drop files")
        self.inp.setMaximumHeight(120); self.inp.setFont(QFont("Segoe UI",11)); inl.addWidget(self.inp)
        self.inp.installEventFilter(self)
        br = QHBoxLayout(); br.addStretch()
        for txt, obj, slot in [("🗑️","clearBtn",self._clear),("📥","exportBtn",self._export),
                                ("⏹","stopBtn",self._stop),("▶","sendBtn",self._send)]:
            b = QPushButton(txt); b.setObjectName(obj); b.setFixedSize(32,32)
            if obj == "stopBtn": b.setEnabled(False); b.clicked.connect(slot)
            else: b.clicked.connect(slot)
            br.addWidget(b)
            if obj=="stopBtn": self.stop_b = b
            if obj=="sendBtn": self.send_b = b
        inl.addLayout(br); lay.addWidget(inf)

    def _connect(self):
        self.backend.stream_token.connect(self._on_tok)
        self.backend.stream_end.connect(self._on_end)
        self.backend.stream_start.connect(lambda: setattr(self, '_stream_buffer', ''))
        self.backend.stats_updated.connect(lambda s: self._upd_ctx())
        self.session.messages_changed.connect(self._render_history)
        self.sc.currentIndexChanged.connect(lambda: setattr(self.session, 'current_skill', self.sc.currentData()) or self._upd_ctx())
        self.ag_cb.toggled.connect(lambda v: setattr(self.session, 'agent_mode', v))
        self.rag_cb.toggled.connect(lambda v: setattr(self, '_rag_on', v))
        self.inp.files_dropped.connect(self._on_drop)

    def eventFilter(self, obj, event):
        if obj == self.inp and event.type() == event.Type.KeyPress:
            if event.key() == Qt.Key_Up and not (event.modifiers() & Qt.ShiftModifier):
                c = self.inp.textCursor()
                if c.position() == 0:
                    self.inp.setPlainText(self.input_history.previous(self.session.session_id, self.inp.toPlainText()))
                    c = self.inp.textCursor(); c.movePosition(c.End); self.inp.setTextCursor(c)
                    return True
            elif event.key() == Qt.Key_Down and not (event.modifiers() & Qt.ShiftModifier):
                c = self.inp.textCursor()
                if c.atEnd():
                    self.inp.setPlainText(self.input_history.next(self.session.session_id, self.inp.toPlainText()))
                    return True
            elif event.key() == Qt.Key_Return and not (event.modifiers() & Qt.ShiftModifier):
                self._send(); return True
        return super().eventFilter(obj, event)

    def _show_welcome(self):
        if not self.session.messages:
            self._welcome = WelcomeWidget()
            self._welcome.skill_selected.connect(self._wel_skill)
            self._welcome.example_clicked.connect(self._wel_ex)
            self.sc_l.insertWidget(self.sc_l.count()-1, self._welcome)

    def _rm_welcome(self):
        if self._welcome:
            self.sc_l.removeWidget(self._welcome); self._welcome.deleteLater(); self._welcome = None

    def _wel_skill(self, s):
        self.sc.setCurrentIndex(list(SKILLS.keys()).index(s)); self.inp.setFocus()
    def _wel_ex(self, t):
        self._rm_welcome(); self.inp.setPlainText(t); self.inp.setFocus()

    def _on_drop(self, files):
        self._rm_welcome()
        parts = []
        for p, c in files:
            n = Path(p).name; e = Path(p).suffix.lstrip('.')
            l = {'py':'python','js':'javascript','ts':'typescript'}.get(e, e)
            parts.append(f"File: `{n}`\n```{l}\n{c}\n```")
        cur = self.inp.toPlainText().strip()
        self.inp.setPlainText(("\n\n".join(parts) + "\n\n" + cur) if cur else "\n\n".join(parts))
        self.toast.info(f"Attached {len(files)} file(s)")

    def insert_file_content(self, path, content):
        self._rm_welcome()
        n = Path(path).name; e = Path(path).suffix.lstrip('.')
        l = {'py':'python','js':'javascript','ts':'typescript','cpp':'cpp','c':'c','rs':'rust','go':'go'}.get(e, e)
        blk = f"File: `{n}`\n```{l}\n{content}\n```"
        cur = self.inp.toPlainText().strip()
        self.inp.setPlainText(f"Review this file:\n\n{blk}\n\n{cur}" if cur else f"Review this file:\n\n{blk}")
        self.inp.setFocus()

    def _render_history(self):
        while self.sc_l.count() > 1:
            it = self.sc_l.takeAt(0)
            if it.widget(): it.widget().deleteLater()
        for m in self.session.messages:
            b = EnhancedMessageBubble(m)
            b.run_code_requested.connect(self.run_code_requested.emit)
            b.save_file_requested.connect(lambda c, p: self._save_f(c, p))
            self.sc_l.insertWidget(self.sc_l.count()-1, b)
        self._upd_ctx()
        QTimer.singleShot(50, lambda: self.scroll.verticalScrollBar().setValue(self.scroll.verticalScrollBar().maximum()))

    def _upd_ctx(self):
        sk = SKILLS[self.session.current_skill]; cm = self.backend.context_manager
        _, t = cm.build_context(self.session.messages, sk, self._sys_override)
        self.ctx_l.setText(f"Context: ~{t} / {self.backend._n_ctx}t")

    def _send(self):
        if self._generating: return
        txt = self.inp.toPlainText().strip()
        if not txt: return
        self._rm_welcome(); self.inp.clear()
        sk = self.sc.currentData(); self.session.current_skill = sk
        self.input_history.add(self.session.session_id, txt); self.input_history.reset(self.session.session_id)
        self.session.add_message(Role.USER, txt, skill=sk)
        if self.session.agent_mode: self.agent_requested.emit(txt)
        else: self._gen(txt, sk)

    def _gen(self, txt, sk_name):
        self._generating = True; self._stream_buffer = ""
        self.send_b.setEnabled(False); self.stop_b.setEnabled(True); self.inp.setEnabled(False)
        sk = SKILLS[sk_name]; cm = self.backend.context_manager
        msgs, _ = cm.build_context(self.session.messages, sk, self._sys_override)
        if self._rag_on and not self.session.agent_mode:
            rc = self.rag.retrieve(txt)
            if rc:
                if msgs and msgs[0]["role"]=="system": msgs[0]["content"] += "\n\n" + rc
                else: msgs.insert(0, {"role":"system","content":rc})
        self.plugins.execute(HookPoint.BEFORE_GENERATION, messages=msgs, skill=sk, session=self.session)
        msg = Message(role=Role.ASSISTANT, content="", skill=sk_name)
        self.session.messages.append(msg)
        self._streaming_bubble = EnhancedMessageBubble(msg)
        self._streaming_bubble.run_code_requested.connect(self.run_code_requested.emit)
        self._streaming_bubble.save_file_requested.connect(lambda c, p: self._save_f(c, p))
        self.sc_l.insertWidget(self.sc_l.count()-1, self._streaming_bubble)
        self.scroll.verticalScrollBar().setValue(self.scroll.verticalScrollBar().maximum())
        def _r():
            stats = self.backend.generate(msgs, sk, stream=True)
            msg.token_count = stats.completion_tokens; msg.content = self._stream_buffer
            self.session._save()
            self.plugins.execute(HookPoint.AFTER_GENERATION, message=msg, stats=stats, session=self.session)
        threading.Thread(target=_r, daemon=True).start()

    def _on_tok(self, t):
        if self._streaming_bubble:
            self._stream_buffer += t; self._streaming_bubble.append_text(t)
            if len(self._stream_buffer) % 80 < len(t):
                self.scroll.verticalScrollBar().setValue(self.scroll.verticalScrollBar().maximum())

    def _on_end(self):
        if self._generating:
            self._generating = False; self.send_b.setEnabled(True); self.stop_b.setEnabled(False)
            self.inp.setEnabled(True); self.inp.setFocus()
            if self._streaming_bubble: self._streaming_bubble.finalize_streaming(self._stream_buffer)
            self._render_history()

    def _stop(self): self._generating = False; self.backend.stream_end.emit()
    def _save_f(self, c, p):
        try: Path(p).write_text(c, encoding='utf-8'); self.toast.success(f"Saved {p}")
        except Exception as e: self.toast.error(str(e))

    def _override_sys(self):
        sk = SKILLS[self.session.current_skill]
        d = SystemPromptDialog(self._sys_override or sk.system_prompt, sk.display_name, self)
        if d.exec() == QDialog.Accepted:
            self._sys_override = d.get_prompt()
            self.sp_btn.setText("📝 Sys ✏️" if self._sys_override else "📝 Sys")

    def _clear(self):
        if QMessageBox.question(self,"","Clear?")==QMessageBox.Yes:
            self.session.clear(); self._sys_override=""; self.sp_btn.setText("📝 Sys"); self._show_welcome()

    def _export(self):
        p,_ = QFileDialog.getSaveFileName(self,"Export",f"{self.session.title}.md","MD (*.md);;JSON (*.json)")
        if p:
            if p.endswith('.json'):
                Path(p).write_text(json.dumps({"title":self.session.title,"messages":[{"role":m.role.value,"content":m.content} for m in self.session.messages]},indent=2), encoding='utf-8')
            else: Path(p).write_text(self.session.export_markdown(), encoding='utf-8')
            self.toast.success(f"Exported {p}")

    def add_agent_step(self, st, c):
        self.sc_l.insertWidget(self.sc_l.count()-1, AgentStepWidget(st, c))
        self.scroll.verticalScrollBar().setValue(self.scroll.verticalScrollBar().maximum())

    def showEvent(self, e): super().showEvent(e); self.inp.setFocus()

# ═══════════════════════════════════════════════════════════════════════════════
# AUTO-TITLER
# ═══════════════════════════════════════════════════════════════════════════════
class AutoTitler(QObject):
    SYS = "Generate a 3-6 word title. Output ONLY the title. No quotes, no punctuation."
    def __init__(self, backend, parent=None): super().__init__(parent); self.backend=backend; self._c=0
    def generate(self, msg, cb):
        self._c+=1
        def _r():
            msgs=[{"role":"system","content":self.SYS},{"role":"user","content":msg[:300]}]
            t=""; evt=threading.Event()
            def tok(s): nonlocal t; t+=s
            def end(): evt.set()
            self.backend.stream_token.connect(tok); self.backend.stream_end.connect(end)
            self.backend.stream_start.emit()
            tiny=SkillConfig("t","","","",0,0.3,0.8,0.5,0.2,["\n",".","!","?","<|im_end|>","</s>"],0.3)
            self.backend.generate(msgs, tiny, stream=True); evt.wait(30)
            self.backend.stream_token.disconnect(tok); self.backend.stream_end.disconnect(end)
            t=t.strip().strip('"').strip("'").strip()
            if len(t)>50: t=t[:50]+"…"
            if not t: t=f"Chat {self._c}"
            QTimer.singleShot(0, lambda: cb(t))
        threading.Thread(target=_r, daemon=True).start()

# ═══════════════════════════════════════════════════════════════════════════════
# STATUS BAR
# ═══════════════════════════════════════════════════════════════════════════════
class StatusBar(QFrame):
    def __init__(self, backend, parent=None):
        super().__init__(parent); self.backend=backend; self.setObjectName("statusBar"); self.setFixedHeight(28)
        l=QHBoxLayout(self); l.setContentsMargins(12,2,12,2); l.setSpacing(16)
        self.ml=QLabel("📝 No model"); self.ml.setObjectName("statusItem"); l.addWidget(self.ml)
        self.sl=QLabel("⚡ — t/s"); self.sl.setObjectName("statusItem"); l.addWidget(self.sl)
        self.tl=QLabel("📊 0/0t"); self.tl.setObjectName("statusItem"); l.addWidget(self.tl)
        self.templ=QLabel("🌡️ —"); self.templ.setObjectName("statusItem"); l.addWidget(self.templ)
        self.mockl=QLabel(""); self.mockl.setObjectName("mockLabel"); l.addWidget(self.mockl)
        l.addStretch(); l.addWidget(QLabel(f"v{VERSION}"))
        self.backend.stats_updated.connect(self._stats); self.backend.model_loaded.connect(self._loaded)
        self.backend.error_occurred.connect(lambda e: self.mockl.setText(f"⚠️ {e[:60]}"))

    def _loaded(self, ok):
        if ok:
            if self.backend._use_mock: self.ml.setText("📝 Mock"); self.mockl.setText("⚠️ Install llama-cpp-python")
            else: self.ml.setText(f"📝 {Path(self.backend._model_path).stem}"); self.mockl.setText("")
    def _stats(self, s):
        self.sl.setText(f"⚡ {s.tokens_per_second:.1f} t/s")
        self.tl.setText(f"📊 {s.prompt_tokens}+{s.completion_tokens}t")
    def set_temp(self, t): self.templ.setText(f"🌡️ {t}")

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN WINDOW
# ═══════════════════════════════════════════════════════════════════════════════
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("🔧 AI Coding Assistant"); self.setMinimumSize(1100,750); self.resize(1400,900)
        # Core
        self.backend = LlamaBackend(self); self.tools = ToolRegistry()
        self.templates = PromptTemplates(); self.branch_mgr = BranchManager()
        self.snippet_lib = SnippetLibrary(); self.input_hist = InputHistoryManager()
        self.rag = RAGLiteInjector(self.tools); self.plugins = PluginSystem(self)
        self.toast = ToastManager(self); self.task_mgr = TaskManager(self)
        self.model_mgr = ModelManager(self.backend, self); self.agent = AgentOrchestrator(self.backend, self.tools, self)
        self._chats: Dict[str, ChatWidget] = {}; self._cur: Optional[str] = None
        self._titled: set = set(); self._pinned: set = set()
        self._ui(); self._theme(); self._connect(); self._load_state()
        self.plugins.load_plugins()
        self.titler = AutoTitler(self.backend, self)

    def _ui(self):
        c = QWidget(); self.setCentralWidget(c)
        ml = QHBoxLayout(c); ml.setContentsMargins(0,0,0,0); ml.setSpacing(0)
        # Sidebar
        sb = QWidget(); sb.setFixedWidth(220); sb.setObjectName("sidebar")
        sbl = QVBoxLayout(sb); sbl.setContentsMargins(0,0,0,0); sbl.setSpacing(0)
        ah = QFrame(); ah.setFixedHeight(48); ah.setObjectName("appHeader")
        ahl = QHBoxLayout(ah); ahl.setContentsMargins(12,0,12,0)
        al = QLabel("🔧"); al.setFont(QFont("",20)); ahl.addWidget(al)
        ahl.addWidget(QLabel("AI Assistant"))
        sbl.addWidget(ah)
        self.cl = ChatListPanel(); sbl.addWidget(self.cl,1)
        mb = QFrame(); mb.setObjectName("modelBar"); mbl = QHBoxLayout(mb); mbl.setContentsMargins(8,4,8,4)
        self.modl = QLabel("🧠 Mock"); self.modl.setObjectName("modelLabel"); self.modl.setCursor(Qt.PointingHandCursor)
        self.modl.mouseDoubleClickEvent = lambda e: ModelSwitcherDialog(self.model_mgr, self.backend, self).exec()
        mbl.addWidget(self.modl,1)
        sw = QPushButton("🔄"); sw.setFixedSize(24,24); sw.setObjectName("titleBarBtn")
        sw.clicked.connect(lambda: ModelSwitcherDialog(self.model_mgr, self.backend, self).exec()); mbl.addWidget(sw)
        sbl.addWidget(mb); ml.addWidget(sb)
        # Center
        ctl = QVBoxLayout(); ctl.setContentsMargins(0,0,0,0); ctl.setSpacing(0)
        tb = QFrame(); tb.setObjectName("titleBar"); tb.setFixedHeight(42)
        tbl = QHBoxLayout(tb); tbl.setContentsMargins(12,0,8,0); tbl.setSpacing(2)
        self.ttl = QLabel("New Chat"); self.ttl.setObjectName("titleLabel"); tbl.addWidget(self.ttl); tbl.addStretch()
        self._tbb = {}
        for ico, tip, slot in [
            ("📝","Templates (Ctrl+T)",self._tmpl_menu),("🛠️","Skills (Ctrl+Shift+S)",self._skill_ed),
            ("📊","Analytics (Ctrl+D)",lambda: TokenAnalyticsDialog(self.cl._sessions, self.backend, self).exec()),
            ("📚","Snippets",self._snippets),("📥","Import",self._import),("⬇️","Download Models",self._dl_model),
            ("📂","Files (Ctrl+B)",self._tog_fb),("▶️","Runner (Ctrl+R)",self._tog_cr),
            ("⏳","Tasks",self._tog_tp),("🌿","Branch",self._branch),("⚙️","Settings",self._settings)]:
            b = QPushButton(ico); b.setObjectName("tbBtn"); b.setFixedSize(28,28); b.setToolTip(tip); b.clicked.connect(slot)
            if ico=="📂": b.setCheckable(True); self.fb_btn=b
            elif ico=="▶️": b.setCheckable(True); self.cr_btn=b
            elif ico=="⏳": b.setCheckable(True); self.tp_btn=b
            tbl.addWidget(b); self._tbb[ico]=b
        ctl.addWidget(tb)
        self.splitter = QSplitter(Qt.Horizontal)
        self.stack = QStackedWidget(); self.splitter.addWidget(self.stack)
        self.fb = FileBrowserPanel(self.tools); self.fb.setMinimumWidth(200); self.fb.setMaximumWidth(350); self.fb.hide()
        self.fb.file_insert_requested.connect(self._file_ins); self.splitter.addWidget(self.fb)
        self.cr = CodeRunnerPanel(self.tools); self.cr.setMinimumWidth(250); self.cr.setMaximumWidth(400); self.cr.hide()
        self.splitter.addWidget(self.cr)
        self.tp = TaskManagerWidget(self.task_mgr); self.tp.setMinimumWidth(200); self.tp.setMaximumWidth(300); self.tp.hide()
        self.splitter.addWidget(self.tp)
        self.splitter.setStretchFactor(0,1)
        for i in range(1,4): self.splitter.setStretchFactor(i,0)
        ctl.addWidget(self.splitter,1)
        self.sbar = StatusBar(self.backend); ctl.addWidget(self.sbar)
        ml.addLayout(ctl,1)

    def _connect(self):
        self.cl.chat_selected.connect(self._switch)
        self.cl.new_chat_requested.connect(self._new_chat)
        self.cl.lw.setContextMenuPolicy(Qt.CustomContextMenu)
        self.cl.lw.customContextMenuRequested.connect(self._sess_ctx)
        self.backend.model_loaded.connect(self._on_loaded)
        self.model_mgr.model_changed.connect(self._on_mchanged)
        self.agent.step_signal.connect(self._ag_step)
        self.agent.finished.connect(self._ag_done)
        self.agent.error.connect(lambda e: self.toast.error(f"Agent: {e}"))
        self.tmpl_menu_obj = TemplatesMenu(self.templates)
        self.tmpl_menu_obj.template_selected.connect(self._on_tmpl)

    def _load_state(self):
        cp = Path.home()/".ai_coding_assistant"/"config.json"
        if cp.exists():
            try:
                d=json.loads(cp.read_text())
                if d.get("model_path"): self.backend.configure(d["model_path"],d.get("n_ctx",DEFAULT_CTX),d.get("n_threads",DEFAULT_THREADS),d.get("n_gpu_layers",DEFAULT_GPU_LAYERS))
                if d.get("working_dir"): self.tools.working_dir=Path(d["working_dir"]).resolve()
                self._pinned=set(d.get("pinned",[]))
            except: pass
        em = os.environ.get("LLAMA_MODEL","")
        if em and not self.backend._model_path: self.backend.configure(model_path=em)
        # Load custom skills
        sp = Path.home()/".ai_coding_assistant"/"custom_skills.json"
        if sp.exists():
            try:
                for n,d in json.loads(sp.read_text()).items():
                    if n not in SKILLS:
                        s=SkillConfig(n,d.get("display_name",n),d.get("icon","🔧"),d.get("system_prompt",""),
                            d.get("max_output_tokens",1024),d.get("temperature",0.7),d.get("top_p",0.95),
                            d.get("frequency_penalty",0.3),d.get("presence_penalty",0.1),
                            d.get("stop_tokens",[]),d.get("context_budget_ratio",0.6),d.get("include_full_history",False),d.get("description",""))
                        s.custom=True; SKILLS[n]=s
            except: pass
        self.backend.load_model()
        if not self.cl._sessions: self.cl.new_chat()
        self.task_mgr.submit("Indexing", lambda:(self.rag.build_index(),None)[1],
            on_complete=lambda t: self.toast.info(f"RAG: {len(self.rag._cache)} files"))
        if self.plugins._loaded: QTimer.singleShot(1000, lambda: self.toast.info(f"Plugins: {', '.join(self.plugins._loaded)}"))

    def _switch(self, sid):
        if sid==self._cur: return
        if self._cur and self._cur in self._chats: self._chats[self._cur].session._save()
        self._cur=sid; s=self.cl._sessions[sid]; self.ttl.setText(s.title)
        if sid not in self._chats:
            w=ChatWidget(s,self.backend,self.tools,self.templates,self.branch_mgr,self.input_hist,self.rag,self.plugins,self.toast)
            w.send_requested.connect(self._on_send); w.agent_requested.connect(self._on_agent)
            w.run_code_requested.connect(self._on_run); self._chats[sid]=w; self.stack.addWidget(w)
        self.stack.setCurrentIndex(self.stack.indexOf(self._chats[sid]))
        self.sbar.set_temp(SKILLS[s.current_skill].temperature)

    def _new_chat(self):
        if self.cl._sessions: self._switch(list(self.cl._sessions.keys())[-1])

    def _on_send(self, t, sk):
        self.sbar.set_temp(SKILLS[sk].temperature)
        if self._cur and self._cur not in self._titled:
            s=self.cl._sessions[self._cur]
            if len([m for m in s.messages if m.role==Role.USER])<=1:
                self._titled.add(self._cur)
                self.titler.generate(t, lambda title, sid=self._cur: self._auto_title(sid, title))

    def _auto_title(self, sid, title):
        if sid in self.cl._sessions:
            self.cl.rename_current(title)
            if sid==self._cur: self.ttl.setText(title)

    def _on_agent(self, t):
        if self._cur and self._cur in self._chats:
            self._chats[self._cur].add_agent_step("thinking","Agent starting...")
            self.agent.run(t, self._chats[self._cur].session.messages)

    def _ag_step(self, st, c):
        if self._cur and self._cur in self._chats: self._chats[self._cur].add_agent_step(st,c)
    def _ag_done(self, a):
        if self._cur: self.cl._sessions[self._cur].add_message(Role.ASSISTANT, a, skill="agent")

    def _on_run(self, code, lang):
        if not self.cr.isVisible(): self._tog_cr()
        self.cr.run_code(code, lang)

    def _file_ins(self, p, c):
        if self._cur and self._cur in self._chats: self._chats[self._cur].insert_file_content(p,c)

    def _sess_ctx(self, pos):
        it=self.cl.lw.itemAt(pos)
        if not it: return
        sid=list(self.cl._sessions.keys())[it.row()]
        m=SessionContextMenu(sid,self.cl._sessions[sid].title,sid in self._pinned)
        m.rename_requested.connect(self._rename)
        m.duplicate_requested.connect(self._dup)
        m.export_requested.connect(self._export_sp)
        m.pin_toggled.connect(self._pin)
        m.archive_requested.connect(self._archive)
        m.exec_(self.cl.lw.mapToGlobal(pos))

    def _rename(self, sid):
        n,ok=QInputDialog.getText(self,"","Name:",text=self.cl._sessions[sid].title)
        if ok and n.strip():
            self.cl._sessions[sid].title=n.strip(); self.cl._sessions[sid]._save(); self.cl._refresh_list()
            if sid==self._cur: self.ttl.setText(n.strip())

    def _dup(self, sid):
        s=self.cl._sessions[sid]; nid=f"chat_{int(time.time()*1000)}"
        ns=ChatSession(nid,f"{s.title} (copy)")
        ns.messages=[Message(m.role,m.content,m.timestamp,m.token_count,m.meta,m.skill) for m in s.messages]
        ns.current_skill=s.current_skill; ns.messages_changed.emit()
        self.cl.add_session(ns); self.toast.success("Duplicated")

    def _export_sp(self, sid):
        as_json=sid.endswith(":json"); sid=sid.replace(":json","")
        s=self.cl._sessions.get(sid)
        if not s: return
        ext="json" if as_json else "md"
        p,_=QFileDialog.getSaveFileName(self,"Export",f"{s.title}.{ext}",f"{'JSON' if as_json else 'MD'} (*.{ext})")
        if p:
            if as_json: Path(p).write_text(json.dumps({"title":s.title,"messages":[{"role":m.role.value,"content":m.content} for m in s.messages]},indent=2),encoding='utf-8')
            else: Path(p).write_text(s.export_markdown(),encoding='utf-8')

    def _pin(self, sid, pin):
        if pin: self._pinned.add(sid)
        else: self._pinned.discard(sid)
        self._save_cfg(); self.toast.info("Pinned" if pin else "Unpinned")

    def _archive(self, sid):
        if QMessageBox.question(self,"","Archive?")==QMessageBox.Yes:
            p=CHAT_DIR/f"{sid}.json"; ad=CHAT_DIR/"archive"; ad.mkdir(exist_ok=True)
            if p.exists(): shutil.move(str(p),str(ad/p.name))
            if sid in self.cl._sessions: del self.cl._sessions[sid]
            self.cl._refresh_list()
            if sid==self._cur and self.cl._sessions: self._switch(list(self.cl._sessions.keys())[0])

    def _tog_fb(self): self.fb.setVisible(not self.fb.isVisible()); self.fb_btn.setChecked(self.fb.isVisible())
    def _tog_cr(self): self.cr.setVisible(not self.cr.isVisible()); self.cr_btn.setChecked(self.cr.isVisible())
    def _tog_tp(self): self.tp.setVisible(not self.tp.isVisible()); self.tp_btn.setChecked(self.tp.isVisible())

    def _tmpl_menu(self):
        b=self._tbb.get("📝")
        if b: self.tmpl_menu_obj.exec_(b.mapToGlobal(QPoint(0,b.height())))

    def _on_tmpl(self, tid):
        if tid=="__create__": CustomTemplateCreator(self.templates,self).exec(); self.tmpl_menu_obj._build(); return
        try: t=self.templates.templates[tid]
        except: return
        d=TemplateDialog(t,self)
        if d.exec()==QDialog.Accepted:
            v=d.get_values(); r,sk=self.templates.render(tid,**v)
            if self._cur and self._cur in self._chats:
                w=self._chats[self._cur]; w.sc.setCurrentIndex(list(SKILLS.keys()).index(sk))
                w.inp.setPlainText(r); w.inp.setFocus()

    def _skill_ed(self):
        ld=QDialog(self); ld.setWindowTitle("🛠️ Skills"); ld.setMinimumSize(450,500)
        ll=QVBoxLayout(ld)
        ll.addWidget(QLabel("Tailored inference harnesses. Click to edit."))
        sl=QListWidget(); sl.setObjectName("searchResults")
        for k,s in SKILLS.items():
            it=QListWidgetItem(f"{s.icon} {s.display_name}{' ✨' if s.custom else ''}\n  temp={s.temperature} out={s.max_output_tokens} budget={int(s.context_budget_ratio*100)}%")
            it.setData(Qt.UserRole,k); sl.addItem(it)
        ll.addWidget(sl,1)
        br=QHBoxLayout(); br.addStretch()
        nb=QPushButton("➕ New"); nb.setObjectName("sendBtn")
        eb=QPushButton("✏️ Edit"); eb.setObjectName("titleBarBtn")
        br.addWidget(nb); br.addWidget(eb); ll.addLayout(br)
        def edit():
            it=sl.currentItem()
            if not it: return
            ed=SkillEditorDialog(SKILLS[it.data(Qt.UserRole)],ld)
            ed.skill_saved.connect(self._skill_saved); ed.exec()
        nb.clicked.connect(lambda: (SkillEditorDialog(None,ld).skill_saved.connect(self._skill_saved), SkillEditorDialog(None,ld).exec()))
        eb.clicked.connect(edit); sl.itemDoubleClicked.connect(lambda: edit())
        ld.exec()

    def _skill_saved(self, d):
        if d.get("_delete"): SKILLS.pop(d["name"],None)
        else:
            s=SkillConfig(d["name"],d["display_name"],d["icon"],d["system_prompt"],d["max_output_tokens"],d["temperature"],d["top_p"],d["frequency_penalty"],d["presence_penalty"],d["stop_tokens"],d["context_budget_ratio"],d["include_full_history"],d.get("description",""))
            s.custom=d.get("custom",False); SKILLS[d["name"]]=s
        custom={k:{"display_name":v.display_name,"icon":v.icon,"system_prompt":v.system_prompt,"max_output_tokens":v.max_output_tokens,"temperature":v.temperature,"top_p":v.top_p,"frequency_penalty":v.frequency_penalty,"presence_penalty":v.presence_penalty,"stop_tokens":v.stop_tokens,"context_budget_ratio":v.context_budget_ratio,"include_full_history":v.include_full_history,"description":v.description} for k,v in SKILLS.items() if v.custom}
        (Path.home()/".ai_coding_assistant"/"custom_skills.json").write_text(json.dumps(custom,indent=2))
        for w in self._chats.values():
            c=w.sc.currentData(); w.sc.blockSignals(True); w.sc.clear()
            for k,sk in SKILLS.items(): w.sc.addItem(f"{sk.icon} {sk.display_name}",k)
            if c in SKILLS: w.sc.setCurrentIndex(list(SKILLS.keys()).index(c))
            w.sc.blockSignals(False)
        self.toast.success("Skill saved")

    def _snippets(self):
        d=SnippetDialog(self.snippet_lib,self); d.snippet_selected.connect(self._ins_snip); d.exec()
    def _ins_snip(self, n, c):
        if self._cur and self._cur in self._chats:
            w=self._chats[self._cur]; w._rm_welcome()
            w.inp.setPlainText(f"Snippet '{n}':\n\n```python\n{c}\n```"); w.inp.setFocus()

    def _import(self):
        d=ChatImportDialog(self)
        if d.exec()==QDialog.Accepted:
            r=d.get_result()
            if r and r.get("messages"):
                sid=f"chat_{int(time.time()*1000)}"; s=ChatSession(sid,f"Imported {len(r['messages'])} msgs")
                for m in r["messages"]:
                    rl=Role(m.get("role","user"))
                    if rl in (Role.USER,Role.ASSISTANT): s.messages.append(Message(rl,m.get("content","")))
                s.messages_changed.emit(); self.cl.add_session(s); self.toast.success("Imported")

    def _dl_model(self):
        d=ModelDownloadDialog(self); d.model_downloaded.connect(self._model_dl_done); d.exec()

    def _model_dl_done(self, p):
        n=Path(p).stem
        if QMessageBox.question(self,"","Add and load?")==QMessageBox.Yes:
            self.model_mgr.add_model(n,p); self.model_mgr.switch_to(n)

    def _branch(self):
        if not self._cur: return
        s=self.cl._sessions[self._cur]
        if not s.messages: return
        lu=-1
        for i,m in enumerate(s.messages):
            if m.role==Role.USER: lu=i
        n,ok=QInputDialog.getText(self,"","Branch name:",text=f"Fork msg {lu+1}")
        if ok and n.strip():
            bid=self.branch_mgr.fork(s,lu,n.strip()); nsid=f"chat_{int(time.time()*1000)}"
            ns=ChatSession(nsid,n.strip()); ns.messages=list(self.branch_mgr.get_messages(bid))
            ns.current_skill=s.current_skill; ns.messages_changed.emit()
            self.cl.add_session(ns); self.toast.success("Branch created")

    def _settings(self):
        SettingsDialog(self.backend,self.tools).exec(); self._save_cfg()
        self.task_mgr.submit("Re-index",lambda:(self.rag.build_index(),None)[1])

    def _on_loaded(self, ok):
        if ok:
            if self.backend._use_mock: self.modl.setText("🧠 Mock"); self.modl.setStyleSheet("color:#d29922;")
            else:
                n=self.model_mgr.active_model or Path(self.backend._model_path).stem
                self.modl.setText(f"🧠 {n}"); self.modl.setStyleSheet("color:#7ee787;")
            self.plugins.execute(HookPoint.ON_MODEL_LOADED,backend=self.backend,model_path=self.backend._model_path)

    def _on_mchanged(self, p, n):
        self.modl.setText(f"🧠 {n}"); self.modl.setStyleSheet("color:#7ee787;"); self.toast.success(f"Switched to {n}")

    def _save_cfg(self):
        (Path.home()/".ai_coding_assistant"/"config.json").write_text(json.dumps({
            "model_path":self.backend._model_path,"n_ctx":self.backend._n_ctx,
            "n_threads":self.backend._n_threads,"n_gpu_layers":self.backend._n_gpu_layers,
            "working_dir":str(self.tools.working_dir),"pinned":list(self._pinned)},indent=2))

    def _theme(self):
        self.setStyleSheet("""
        QMainWindow,QWidget{background:#0d1117;color:#c9d1d9;font-family:'Segoe UI',sans-serif;font-size:13px;}
        #appHeader{background:#010409;border-bottom:1px solid #21262d;}
        #sidebar{background:#010409;border-right:1px solid #21262d;}
        #sidebarHeader{color:#58a6ff;font-size:15px;font-weight:bold;padding:12px;}
        #modelBar{background:#010409;border-top:1px solid #21262d;}
        #modelLabel{color:#8b949e;font-size:11px;}
        #chatList{background:transparent;border:none;outline:none;}
        #chatList::item{padding:8px 12px;border-radius:6px;margin:1px 4px;color:#8b949e;}
        #chatList::item:selected{background:#1f2937;color:#f0f6fc;}
        #chatList::item:hover{background:#161b22;}
        #newChatBtn,#deleteChatBtn{background:#21262d;color:#c9d1d9;border:1px solid #30363d;border-radius:6px;padding:6px;font-size:12px;}
        #newChatBtn:hover,#deleteChatBtn:hover{background:#30363d;}
        #titleBar{background:#010409;border-bottom:1px solid #21262d;}
        #titleLabel{color:#f0f6fc;font-size:15px;font-weight:bold;}
        #tbBtn{background:transparent;color:#8b949e;border:none;border-radius:4px;font-size:14px;}
        #tbBtn:hover{background:#21262d;color:#f0f6fc;}
        #tbBtn:checked{background:#1f2937;color:#58a6ff;}
        #skillBar{background:#161b22;border-bottom:1px solid #21262d;}
        #skillLabel{color:#8b949e;font-size:12px;}
        #skillCombo{background:#0d1117;color:#c9d1d9;border:1px solid #30363d;border-radius:4px;padding:4px 8px;}
        #skillCombo::drop-down{border:none;}
        #skillCombo QAbstractItemView{background:#161b22;color:#c9d1d9;border:1px solid #30363d;selection-background-color:#1f2937;}
        #agentCheck{color:#58a6ff;spacing:4px;}
        #contextLabel{color:#8b949e;font-size:11px;}
        #chatScroll{background:#0d1117;border:none;}
        QScrollBar:vertical{background:#0d1117;width:8px;border:none;}
        QScrollBar::handle:vertical{background:#30363d;border-radius:4px;min-height:30px;}
        QScrollBar::handle:vertical:hover{background:#484f58;}
        QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;}
        #inputFrame{background:#010409;border-top:1px solid #21262d;}
        #chatInput{background:#0d1117;color:#c9d1d9;border:1px solid #21262d;border-radius:8px;padding:8px 12px;font-size:13px;}
        #chatInput:focus{border-color:#58a6ff;}
        #sendBtn{background:#238636;color:white;border:none;border-radius:6px;}
        #sendBtn:hover{background:#2ea043;}#sendBtn:disabled{background:#21262d;color:#484f58;}
        #stopBtn{background:#da3633;color:white;border:none;border-radius:6px;}
        #stopBtn:hover{background:#f85149;}#stopBtn:disabled{background:#21262d;color:#484f58;}
        #clearBtn,#exportBtn{background:#21262d;color:#8b949e;border:1px solid #30363d;border-radius:6px;}
        #clearBtn:hover,#exportBtn:hover{background:#30363d;color:#c9d1d9;}
        #titleBarBtn{background:#21262d;color:#c9d1d9;border:1px solid #30363d;border-radius:4px;padding:2px 10px;font-size:12px;}
        #titleBarBtn:hover{background:#30363d;}
        #statusBar{background:#010409;border-top:1px solid #21262d;}
        #statusItem{color:#8b949e;font-size:11px;}
        #mockLabel{color:#d29922;font-size:11px;}
        QGroupBox{color:#58a6ff;font-weight:bold;border:1px solid #21262d;border-radius:6px;margin-top:12px;padding-top:16px;}
        QGroupBox::title{subcontrol-origin:margin;left:12px;padding:0 4px;}
        QLineEdit,QSpinBox,QComboBox{background:#0d1117;color:#c9d1d9;border:1px solid #30363d;border-radius:4px;padding:4px 8px;}
        QLineEdit:focus,QSpinBox:focus{border-color:#58a6ff;}
        QTextEdit{background:#0d1117;color:#c9d1d9;border:1px solid #21262d;}
        QDialog{background:#0d1117;}
        QMessageBox{background:#161b22;}QMessageBox QLabel{color:#c9d1d9;}
        QPushButton{min-width:70px;padding:5px 14px;}
        """)

    def keyPressEvent(self, e):
        m=e.modifiers(); k=e.key()
        if k==Qt.Key_N and m&Qt.ControlModifier: self.cl.new_chat()
        elif k==Qt.Key_B and m&Qt.ControlModifier: self._tog_fb()
        elif k==Qt.Key_F and m&Qt.ControlModifier and not(m&Qt.ShiftModifier): GlobalSearchDialog(self.cl._sessions,self).exec()
        elif k==Qt.Key_T and m&Qt.ControlModifier: self._tmpl_menu()
        elif k==Qt.Key_S and m&Qt.ControlModifier and m&Qt.ShiftModifier: self._skill_ed()
        elif k==Qt.Key_D and m&Qt.ControlModifier: TokenAnalyticsDialog(self.cl._sessions,self.backend,self).exec()
        elif k==Qt.Key_R and m&Qt.ControlModifier: self._tog_cr()
        else: super().keyPressEvent(e)

    def closeEvent(self, e):
        for w in self._chats.values(): w.session._save()
        self._save_cfg(); self.backend.unload(); super().closeEvent(e)

# ═══════════════════════════════════════════════════════════════════════════════
# EXAMPLE PLUGIN WRITER & ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════
def create_example_plugin():
    pd = Path.home()/".ai_coding_assistant"/"plugins"; pd.mkdir(parents=True,exist_ok=True)
    ep = pd/"example_plugin.py"
    if not ep.exists():
        ep.write_text('''\
"""Example Plugin — Auto-logs token usage."""
def register(ps):
    def log_tokens(**kw):
        s = kw.get("stats")
        if s: print(f"[Plugin] Tokens: {s.total_tokens}, Speed: {s.tokens_per_second:.1f} t/s")
        return kw
    ps.register_hook(ps.HookPoint.AFTER_GENERATION, log_tokens, name="token_logger")
    print("[Example Plugin] Loaded!")
''', encoding='utf-8')

def _show_welcome(w):
    m = QMessageBox(w); m.setIcon(QMessageBox.Information); m.setWindowTitle("Welcome")
    m.setText("<h3>🔧 AI Coding Assistant</h3><p>Running in <b>Mock Mode</b>.</p>"
        "<p>Click <b>⬇️</b> to download a model, or <b>⚙️</b> to set a path.</p>"
        "<p>Or: <code>LLAMA_MODEL=path/to/model.gguf python app.py</code></p>")
    m.setDetailedText("SHORTCUTS:\nCtrl+N New · Ctrl+F Search · Ctrl+T Templates\n"
        "Ctrl+B Files · Ctrl+R Runner · Ctrl+D Analytics\n"
        "Ctrl+Shift+S Skills · ↑/↓ History · Enter Send")
    m.setStandardButtons(QMessageBox.Ok)
    m.setStyleSheet("QMessageBox{background:#161b22;min-width:400px;}QMessageBox QLabel{color:#c9d1d9;}"
        "code{background:#1a2a3a;padding:2px 6px;border-radius:3px;color:#e5c07b;font-family:Consolas,monospace;}"
        "h3{color:#58a6ff;}")
    m.exec()

def main():
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    app = QApplication(sys.argv)
    app.setApplicationName("AI Coding Assistant")
    app.setOrganizationName("AIAssistant")
    app.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app.setFont(QFont("Segoe UI", 10))
    create_example_plugin()
    w = MainWindow(); w.show()
    if not w.backend._model_path: QTimer.singleShot(600, lambda: _show_welcome(w))
    sys.exit(app.exec())

if __name__ == "__main__":
    main()