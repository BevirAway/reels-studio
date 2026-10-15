#!/bin/bash
# Установник Студії. Усе ставиться в ~/.studio (пароль адміністратора не потрібен) і в робочу папку ~/Студія.
#   setup.sh                       перше встановлення: вікна з галочками, ключі, робоча папка, модулі Claude
#   setup.sh --settings            змінити модулі й ключі (ярлик «Налаштування студії»)
#   setup.sh --deps <модуль>       лише докачати потрібне модулю (викликає `studio module on`)
#   setup.sh --auto [--modules montage,voice] [--workspace DIR] [--pack ФАЙЛ.zip|ПАПКА] [--no-claude]
#   Пакет стилю (studio-pack*.zip від Нікіти: стиль/, профіль.md, зразок рілса/) береться й сам із ~/Downloads.
#                                  без вікон (перевірка, встановлення по телефону)
set -u
S="$HOME/.studio"; REPO="$S/repo"; BIN="$S/bin"; LOG="$S/install.log"
ARCH=$(uname -m)                        # arm64 — M-чипи, x86_64 — Intel
HERE="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$S" "$BIN" "$S/venvs" "$S/models"
export PATH="$BIN:$S/node/bin:$HOME/.local/bin:$PATH"
export UV_PYTHON_INSTALL_DIR="$S/python" UV_CACHE_DIR="$S/cache/uv"

MODE=first; AUTO=0; DEPS_ONLY=""; MODS_ARG=""; WS_ARG=""; PACK=""; NO_CLAUDE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --settings) MODE=settings ;;
    --deps) DEPS_ONLY="$2"; shift ;;
    --auto) AUTO=1 ;;
    --modules) MODS_ARG="$2"; shift ;;
    --workspace) WS_ARG="$2"; shift ;;
    --pack) PACK="$2"; shift ;;
    --no-claude) NO_CLAUDE=1 ;;
  esac
  shift
done

# ------------------------------------------------------------------ вивід і вікна
say()  { printf "  %s\n" "$*"; printf "%s %s\n" "$(date +%H:%M:%S)" "$*" >>"$LOG"; }
step() { printf "\n▸ %s\n" "$*"; printf "\n%s ▸ %s\n" "$(date +%H:%M:%S)" "$*" >>"$LOG"; }
run()  { "$@" >>"$LOG" 2>&1; }                      # тихо, усе — у журнал
fail() { say "✗ $*  (подробиці: $LOG)"; [ $AUTO = 1 ] || dlg_info "Щось пішло не так: $*

Надішліть Нікіті файл ~/.studio/install.log — він допоможе."; }

dlg_info() {  # текст
  [ $AUTO = 1 ] && return 0
  osascript - "$1" >/dev/null 2>&1 <<'EOF'
on run argv
  display dialog (item 1 of argv) with title "Студія" buttons {"Далі"} default button "Далі" with icon note
end run
EOF
}

dlg_yesno() {  # текст кнопка_так кнопка_ні → 0 якщо так
  [ $AUTO = 1 ] && return 0
  r=$(osascript - "$1" "$2" "$3" 2>/dev/null <<'EOF'
on run argv
  set r to display dialog (item 1 of argv) with title "Студія" buttons {item 3 of argv, item 2 of argv} default button (item 2 of argv) with icon note
  return button returned of r
end run
EOF
)
  [ "$r" = "$2" ]
}

dlg_choose() {  # підказка, к-сть_типових, типові…, усі… → вибрані рядки
  osascript - "$@" 2>/dev/null <<'EOF'
on run argv
  set p to item 1 of argv
  set n to (item 2 of argv) as integer
  set defs to {}
  if n > 0 then set defs to items 3 thru (2 + n) of argv
  set opts to items (3 + n) thru -1 of argv
  set r to choose from list opts with title "Студія" with prompt p default items defs OK button name "Далі" cancel button name "Скасувати" with multiple selections allowed and empty selection allowed
  if r is false then return "__CANCEL__"
  set AppleScript's text item delimiters to linefeed
  return r as text
end run
EOF
}

dlg_secret() {  # текст, посилання-довідка → значення ("" — пропустити)
  while true; do
    r=$(osascript - "$1" 2>/dev/null <<'EOF'
on run argv
  set r to display dialog (item 1 of argv) default answer "" with hidden answer with title "Студія" buttons {"Як отримати?", "Пропустити", "Зберегти"} default button "Зберегти" with icon note
  return (button returned of r) & linefeed & (text returned of r)
end run
EOF
)
    b=$(printf "%s" "$r" | head -1); v=$(printf "%s" "$r" | sed -n 2p)
    case "$b" in
      "Як отримати?") open "$2" ;;
      "Зберегти") printf "%s" "$v"; return ;;
      *) return ;;
    esac
  done
}

# ------------------------------------------------------------------ модулі
IDS=(montage voice upscale sounds texts research publish)
TITLES=(
  "Монтаж рілсів — головне (≈2 ГБ)"
  "Чистка голосу — студійний звук (≈3 ГБ)"
  "Покращення якості відео (≈1 ГБ)"
  "Звуки для монтажу (Freesound)"
  "Тексти, підписи й каруселі"
  "Дослідження Instagram (платний ключ Apify)"
  "Публікація в Instagram і Telegram"
)
cfg_get() { "$S/venvs/base/bin/python" - "$1" 2>/dev/null <<'EOF'
import json,sys,os
try: c=json.load(open(os.path.expanduser("~/.studio/config.json")))
except Exception: c={}
k=sys.argv[1]
v=c.get("modules",{}).get(k[4:]) if k.startswith("mod:") else c.get(k)
print("" if v is None else (("1" if v else "0") if isinstance(v,bool) else v))
EOF
}

# ------------------------------------------------------------------ програми
dl() { curl -fsSL --retry 3 "$1" -o "$2"; }

install_uv() {
  [ -x "$BIN/uv" ] && return 0
  say "uv (менеджер Python)…"
  curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="$BIN" INSTALLER_NO_MODIFY_PATH=1 sh >>"$LOG" 2>&1
  [ -x "$BIN/uv" ]
}

install_ffmpeg() {
  [ -x "$BIN/ffmpeg" ] && [ -x "$BIN/ffprobe" ] && return 0
  say "ffmpeg (робота з відео)…"
  local a=arm64; [ "$ARCH" = x86_64 ] && a=amd64
  local t; t=$(mktemp -d)
  for b in ffmpeg ffprobe; do
    for ch in release snapshot; do
      dl "https://ffmpeg.martin-riedl.de/redirect/latest/macos/$a/$ch/$b.zip" "$t/$b.zip" 2>>"$LOG" && break
    done
    unzip -oq "$t/$b.zip" -d "$t" && mv "$t/$b" "$BIN/$b" && chmod +x "$BIN/$b"
  done
  rm -rf "$t"
  "$BIN/ffmpeg" -version >/dev/null 2>&1
}

install_node() {
  [ -x "$S/node/bin/node" ] && return 0
  say "Node.js (для рендеру відео)…"
  local a=arm64; [ "$ARCH" = x86_64 ] && a=x64
  local v; v=$(curl -fsSL https://nodejs.org/dist/index.json | "$BIN/py" -c "import json,sys; print([x['version'] for x in json.load(sys.stdin) if x['lts']][0])")
  local t; t=$(mktemp -d)
  dl "https://nodejs.org/dist/$v/node-$v-darwin-$a.tar.gz" "$t/node.tgz" && tar -xzf "$t/node.tgz" -C "$t" \
    && rm -rf "$S/node" && mv "$t/node-$v-darwin-$a" "$S/node"
  rm -rf "$t"
  ln -sf "$S/node/bin/node" "$S/node/bin/npm" "$S/node/bin/npx" "$BIN/"
  [ -x "$S/node/bin/node" ]
}

venv_base() {
  if [ ! -x "$S/venvs/base/bin/python" ]; then
    say "Python…"
    run "$BIN/uv" venv --python 3.12 "$S/venvs/base" || return 1
  fi
  run "$BIN/uv" pip install --python "$S/venvs/base/bin/python" -U pillow numpy requests soundfile opencv-python-headless huggingface_hub
}

write_wrappers() {
  cat >"$BIN/py" <<EOF
#!/bin/bash
exec "$S/venvs/base/bin/python" "\$@"
EOF
  cat >"$BIN/studio" <<EOF
#!/bin/bash
exec "$S/venvs/base/bin/python" "$REPO/plugins/studio/scripts/studio.py" "\$@"
EOF
  chmod +x "$BIN/py" "$BIN/studio"
  # PATH для Термінала і для Claude (його команди запускаються через профіль оболонки)
  for f in "$HOME/.zprofile" "$HOME/.zshrc" "$HOME/.bash_profile"; do
    [ -f "$f" ] || [ "$f" != "$HOME/.bash_profile" ] || continue
    grep -q "studio/bin" "$f" 2>/dev/null || printf '\n# Студія\nexport PATH="$HOME/.studio/bin:$HOME/.studio/node/bin:$HOME/.local/bin:$PATH"\n' >>"$f"
  done
}

install_claude_cli() {
  [ $NO_CLAUDE = 1 ] && return 0
  if [ -x "$HOME/.local/bin/claude" ] || command -v claude >/dev/null 2>&1; then return 0; fi
  say "Claude Code…"
  curl -fsSL https://claude.ai/install.sh | bash >>"$LOG" 2>&1
  [ -x "$HOME/.local/bin/claude" ] || command -v claude >/dev/null 2>&1
}

claude_cmd() { if [ -x "$HOME/.local/bin/claude" ]; then echo "$HOME/.local/bin/claude"; else command -v claude; fi; }

# ------------------------------------------------------------------ залежності модулів
deps_montage() {
  if [ ! -x "$S/node/bin/hyperframes" ]; then
    say "hyperframes (анімації та рендер)…"
    run "$S/node/bin/npm" install -g hyperframes || return 1
  fi
  ln -sf "$S/node/bin/hyperframes" "$BIN/hyperframes"
  say "браузер для рендеру…"
  run "$BIN/hyperframes" browser ensure
  say "навички hyperframes для Claude…"
  run "$BIN/hyperframes" skills update hyperframes hyperframes-core hyperframes-animation hyperframes-audio hyperframes-creative hyperframes-cli talking-head-recut embedded-captions \
    || run "$BIN/hyperframes" skills
  if [ "$ARCH" = arm64 ]; then
    say "Whisper (розпізнавання мови без інтернету, ≈1.6 ГБ)…"
    run "$BIN/uv" pip install --python "$S/venvs/base/bin/python" -U mlx-whisper
    run "$BIN/py" -c "from huggingface_hub import snapshot_download as d; d('mlx-community/whisper-large-v3-turbo')"
  fi
}

venv_torch() {
  if [ ! -x "$S/venvs/torch/bin/python" ]; then
    run "$BIN/uv" venv --python 3.12 "$S/venvs/torch" || return 1
  fi
  say "PyTorch (≈1 ГБ)…"
  run "$BIN/uv" pip install --python "$S/venvs/torch/bin/python" -U torch torchaudio soundfile numpy scipy huggingface_hub
  printf '#!/bin/bash\nexec "%s" "$@"\n' "$S/venvs/torch/bin/python" >"$BIN/tpy"; chmod +x "$BIN/tpy"
}

deps_voice() {
  venv_torch || return 1
  local P="$S/venvs/torch/bin/python"
  say "Resemble Enhance…"
  run "$BIN/uv" pip install --python "$P" celluloid librosa matplotlib omegaconf pandas ptflops resampy rich tabulate tqdm deepspeed \
    && run "$BIN/uv" pip install --python "$P" --no-deps resemble-enhance || return 1
  # numpy 2: fsolve повертає масив → float(...[0])
  run "$P" - <<'EOF'
import resemble_enhance, pathlib
p = pathlib.Path(resemble_enhance.__file__).parent / "enhancer/lcfm/cfm.py"
s = p.read_text(); old = "scipy.optimize.fsolve(lambda a: h(1 / n, a) - 0.5, x0=0))"
if old in s:
    p.write_text(s.replace(old, "scipy.optimize.fsolve(lambda a: h(1 / n, a) - 0.5, x0=0)[0])"))
EOF
  if [ ! -f "$S/models/resemble/enhancer_stage2/hparams.yaml" ]; then
    say "модель голосу (≈700 МБ)…"
    run "$P" -c "from huggingface_hub import snapshot_download as d; d('ResembleAI/resemble-enhance', allow_patterns=['enhancer_stage2/*'], local_dir='$S/models/resemble')"
  fi
  [ -f "$S/models/resemble/enhancer_stage2/hparams.yaml" ]
}

deps_upscale() {
  venv_torch || return 1
  run "$BIN/uv" pip install --python "$S/venvs/torch/bin/python" -U spandrel
  [ -f "$S/models/realesr-general-x4v3.pth" ] || dl https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesr-general-x4v3.pth "$S/models/realesr-general-x4v3.pth"
}

deps_for() {
  case "$1" in
    montage) deps_montage ;;
    voice)   deps_voice ;;
    upscale) deps_upscale ;;
    *) return 0 ;;
  esac
}

# ------------------------------------------------------------------ робоча папка
make_workspace() {
  local W="$1"
  mkdir -p "$W"/{Вхідні,Готово,Проєкти,Профіль,"Мій стиль",Бібліотека/Звуки,Бібліотека/Музика,Публікації,.claude}
  cp "$HERE/workspace/AGENTS.md" "$W/AGENTS.md"                     # системні правила — оновлюються з Студією
  [ -f "$W/Профіль/мої правила.md" ] || cp "$HERE/workspace/мої правила.md" "$W/Профіль/мої правила.md"
  [ -f "$W/Профіль/профіль.md" ] || cp "$HERE/workspace/профіль.md" "$W/Профіль/профіль.md"
  cp "$HERE/workspace/settings.json" "$W/.claude/settings.json"
  cp "$HERE/workspace/ЯК КОРИСТУВАТИСЬ.md" "$W/ЯК КОРИСТУВАТИСЬ.md"
  # стартова бібліотека звуків і музики (не перезаписує свої)
  if [ -d "$HERE/starter/sfx" ]; then cp -n "$HERE/starter/sfx/"* "$W/Бібліотека/Звуки/" 2>/dev/null; fi
  if [ -d "$HERE/starter/music" ]; then cp -n "$HERE/starter/music/"* "$W/Бібліотека/Музика/" 2>/dev/null; fi
  # пакет стилю (особисті матеріали: стиль, чернетка профілю, зразок рілса) — не в публічному репозиторії
  local P="$S/pack"
  if [ -d "$P" ]; then
    [ -d "$P/стиль" ] && cp -Rn "$P/стиль/"* "$W/Мій стиль/" 2>/dev/null
    [ -d "$P/зразок рілса" ] && mkdir -p "$W/Мій стиль/зразок рілса" && cp -Rn "$P/зразок рілса/"* "$W/Мій стиль/зразок рілса/" 2>/dev/null
    if [ -f "$P/профіль.md" ] && grep -q "Заповнюється під час першої розмови" "$W/Профіль/профіль.md"; then
      cp "$P/профіль.md" "$W/Профіль/профіль.md"
    fi
  fi
  # ярлики
  for f in "Налаштування студії" "Оновити студію"; do
    cp "$HERE/workspace/$f.command" "$W/$f.command"; chmod +x "$W/$f.command"
  done
}

setup_plugins() {
  [ $NO_CLAUDE = 1 ] && return 0
  local C; C=$(claude_cmd) || return 1
  if "$C" plugin marketplace list 2>/dev/null | grep -q reels-studio; then
    run "$C" plugin marketplace update reels-studio
  else
    run "$C" plugin marketplace add "$REPO" || return 1
  fi
  local st; st=$("$C" plugin list --json 2>/dev/null)
  for m in studio "${IDS[@]}"; do
    local on=0; [ "$m" = studio ] && on=1; [[ ",$CHOSEN," == *",$m,"* ]] && on=1
    if [ $on = 1 ]; then
      if printf "%s" "$st" | grep -q "\"$m@reels-studio\""; then run "$C" plugin enable "$m@reels-studio"
      else run "$C" plugin install "$m@reels-studio" --scope user; fi
      say "✓ модуль $m"
    elif printf "%s" "$st" | grep -q "\"$m@reels-studio\""; then
      run "$C" plugin disable "$m@reels-studio"; say "· модуль $m вимкнено"
    fi
  done
}

write_config() {
  "$S/venvs/base/bin/python" - "$WS" "$CHOSEN" "$(basename "${PACK:-}" .zip)" <<'EOF'
import json, sys, os, time
p = os.path.expanduser("~/.studio/config.json")
try: c = json.load(open(p))
except Exception: c = {}
ws, chosen, preset = sys.argv[1], [m for m in sys.argv[2].split(",") if m], sys.argv[3]
ids = ["montage","voice","upscale","sounds","texts","research","publish"]
c["workspace"] = ws
c["modules"] = {"studio": True, **{m: m in chosen for m in ids}}
if preset: c["pack"] = preset
c.setdefault("installed_at", time.strftime("%Y-%m-%d %H:%M"))
c["updated_at"] = time.strftime("%Y-%m-%d %H:%M")
json.dump(c, open(p, "w"), ensure_ascii=False, indent=2)
EOF
}

ask_keys() {
  local need_el=0 need_ap=0
  [[ ",$CHOSEN," == *",montage,"* || ",$CHOSEN," == *",sounds,"* ]] && need_el=1
  [[ ",$CHOSEN," == *",research,"* ]] && need_ap=1
  if [ $need_el = 1 ] && [ -z "$("$BIN/studio" key get ELEVENLABS_API_KEY)" ]; then
    v=$(dlg_secret "Ключ ElevenLabs — для точного розпізнавання мови в субтитрах і генерації звуків.

Без ключа теж працює: мову розпізнає Whisper просто на Mac (трохи менш точно).

Вставте ключ (Cmd+V) або натисніть «Пропустити»." "https://elevenlabs.io/app/settings/api-keys")
    [ -n "$v" ] && "$BIN/studio" key set ELEVENLABS_API_KEY "$v" | tee -a "$LOG"
  fi
  if [ $need_ap = 1 ] && [ -z "$("$BIN/studio" key get APIFY_TOKEN)" ]; then
    v=$(dlg_secret "Ключ Apify — щоб Claude міг завантажувати пости й рілси з Instagram.

Вставте ключ (Cmd+V) або натисніть «Пропустити»." "https://console.apify.com/settings/integrations")
    [ -n "$v" ] && "$BIN/studio" key set APIFY_TOKEN "$v" | tee -a "$LOG"
  fi
}

# ================================================================== сценарії
if [ -n "$DEPS_ONLY" ]; then
  install_uv && venv_base >/dev/null && deps_for "$DEPS_ONLY" && say "✓ готово" || fail "не вдалося встановити $DEPS_ONLY"
  exit $?
fi

printf "\n  ✦ Студія рілсів\n  Журнал встановлення: %s\n" "$LOG"
: >"$LOG"

if [ "$MODE" = first ] && [ $AUTO = 0 ]; then
  dlg_info "Привіт! Зараз я встановлю Студію — помічника для рілсів, текстів і публікацій, з яким ви говорите в застосунку Claude.

Спершу оберіть, що вам потрібно. Усе можна змінити пізніше ярликом «Налаштування студії».

Встановлення займе 10–30 хвилин (залежить від інтернету). Mac може попросити дозволів — це нормально."
fi

# ---- вибір модулів
install_uv && venv_base || { fail "не вдалося встановити Python"; exit 1; }
write_wrappers
if [ $AUTO = 1 ]; then
  CHOSEN="${MODS_ARG:-montage,voice,sounds,texts}"
else
  defs=(); opts=()
  for i in "${!IDS[@]}"; do
    m=${IDS[$i]}; t=${TITLES[$i]}
    if [ "$ARCH" = x86_64 ] && { [ $m = voice ] || [ $m = upscale ]; }; then continue; fi   # на Intel дуже повільно
    opts+=("$t")
    cur=$(cfg_get "mod:$m")
    if [ "$cur" = 1 ] || { [ -z "$cur" ] && [[ " montage voice sounds texts " == *" $m "* ]]; }; then defs+=("$t"); fi
  done
  sel=$(dlg_choose "Що встановити? (Cmd+клік — кілька пунктів)" "${#defs[@]}" "${defs[@]}" "${opts[@]}")
  [ "$sel" = "__CANCEL__" ] && { say "Скасовано."; exit 0; }
  CHOSEN=""
  for i in "${!IDS[@]}"; do printf "%s\n" "$sel" | grep -qxF "${TITLES[$i]}" && CHOSEN="$CHOSEN,${IDS[$i]}"; done
  CHOSEN="${CHOSEN#,}"
fi
say "Модулі: studio,${CHOSEN}"

# ---- пакет стилю
if [ -z "$PACK" ]; then PACK=$(ls -t "$HOME/Downloads"/studio-pack*.zip 2>/dev/null | head -1); fi
if [ -n "$PACK" ] && [ -e "$PACK" ]; then
  rm -rf "$S/pack"; mkdir -p "$S/pack"
  if [ -d "$PACK" ]; then cp -R "$PACK/." "$S/pack/"; else
    t=$(mktemp -d); unzip -q "$PACK" -d "$t"
    root=$(dirname "$(find "$t" -maxdepth 3 \( -name "профіль.md" -o -name "стиль" \) | head -1)")
    cp -R "$root/." "$S/pack/"; rm -rf "$t"
  fi
  say "Пакет стилю: $(basename "$PACK")"
fi

# ---- робоча папка
WS="${WS_ARG:-$(cfg_get workspace)}"; WS="${WS:-$HOME/Студія}"

# ---- програми
step "Встановлюю програми"
install_ffmpeg || fail "ffmpeg"
install_node || fail "Node.js"
install_claude_cli || fail "Claude Code"
for m in ${CHOSEN//,/ }; do
  step "Модуль: $m"
  deps_for "$m" || fail "модуль $m"
done

step "Робоча папка"
make_workspace "$WS"; say "✓ $WS"
write_config

step "Модулі в Claude"
setup_plugins || fail "не вдалося підключити модулі до Claude"

[ $AUTO = 1 ] || ask_keys

if [ "$MODE" = settings ] && [ $AUTO = 0 ]; then   # замінити чи додати будь-який ключ
  KN=(ELEVENLABS_API_KEY APIFY_TOKEN IG_TOKEN TG_BOT_TOKEN TG_CHANNEL)
  KT=("ElevenLabs — мова й звуки" "Apify — Instagram-дослідження" "Instagram — токен публікації" "Telegram — токен бота" "Telegram — канал (@назва)")
  KU=("https://elevenlabs.io/app/settings/api-keys" "https://console.apify.com/settings/integrations" "https://developers.facebook.com/apps" "https://t.me/BotFather" "https://t.me")
  opts=(); for i in "${!KN[@]}"; do has=$("$BIN/studio" key get "${KN[$i]}"); opts+=("${KT[$i]}$([ -n "$has" ] && echo " ✓")"); done
  sel=$(dlg_choose "Які ключі додати або замінити? (✓ — уже збережено; можна нічого не обирати)" 0 "${opts[@]}")
  for i in "${!KN[@]}"; do
    printf "%s\n" "$sel" | grep -qF "${KT[$i]}" || continue
    v=$(dlg_secret "${KT[$i]}: вставте значення (Cmd+V)." "${KU[$i]}")
    [ -n "$v" ] && "$BIN/studio" key set "${KN[$i]}" "$v" | tee -a "$LOG"
  done
  "$BIN/studio" key get IG_TOKEN >/dev/null && [ -n "$("$BIN/studio" key get IG_TOKEN)" ] && \
    run "$BIN/py" "$REPO/plugins/publish/scripts/publish.py" setup-ig
fi

step "Перевірка"
"$BIN/studio" doctor | tee -a "$LOG" | sed 's/^/  /'

if [ $AUTO = 0 ]; then
  if [ "$MODE" = first ]; then
    dlg_info "Готово! ✦

Що далі:
1. Відкрийте застосунок Claude і увійдіть у свій акаунт.
2. Вкладка «Code» → оберіть папку «Студія» у вашій домашній папці.
3. Напишіть: «Привіт! Давай налаштуємо студію» — Claude поставить кілька запитань про вас і ваші соцмережі.

Відео для рілсів кладіть у папку «Студія/Вхідні»."
    if [ -d /Applications/Claude.app ]; then open -a Claude; else open "https://claude.ai/download"; fi
    open "$WS"
  else
    dlg_info "Налаштування збережено. Перезапустіть розмову в Claude, щоб він побачив зміни."
  fi
fi
say "Готово."
