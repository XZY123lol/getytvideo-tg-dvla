import telebot
from telebot import types
import yt_dlp
import os
import time
import threading
from urllib.parse import urlparse

TOKEN = '6576464104:AAEs8kZIQC2hCUZfc3YdJ_ISK4eCNCqgcNE'
bot = telebot.TeleBot(TOKEN)

BASE_TEMP_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp_ddvx")
os.makedirs(BASE_TEMP_FOLDER, exist_ok=True)

TEXT_START = "👋 Привет! Отправь ссылку на YouTube или TikTok, я покажу доступные форматы."
TEXT_CANCEL = "❌ Отмена"
TEXT_CANCELLED = "🚫 Отменено. Отправьте новую ссылку."
TEXT_FIRST_SEND_LINK = "❗ Сначала отправьте ссылку на YouTube или TikTok."
TEXT_DOWNLOADING = "⏳ Скачиваем: {}"
TEXT_ANALYZING = "🔎 Анализирую доступные форматы... ⏳"

user_links = {}
user_info = {}
user_selected_formats = {}
download_progress = {}
user_subtitles_info = {}

def safe_filename(name: str) -> str:
    return "".join(c for c in name if c.isalnum() or c in " .-_").rstrip()

def get_info(url: str) -> dict:
    opts = {'quiet': True}
    hostname = urlparse(url).hostname or ""
    if hostname == "tiktok.com" or hostname.endswith(".tiktok.com"):
        opts.update({'extractor_retries': 1})
    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False)

def make_format_buttons(info: dict, selected: set = None) -> types.InlineKeyboardMarkup:
    selected = selected or set()
    markup = types.InlineKeyboardMarkup(row_width=3)
    fmt_list = info.get('formats', [])
    vq = sorted({f['height'] for f in fmt_list if f.get('vcodec') != 'none' and f.get('height')})
    for h in vq:
        key = f"video_{h}"
        txt = f"🎥{h}p" + ("✅" if key in selected else "")
        markup.add(types.InlineKeyboardButton(txt, callback_data=f"toggle_{key}"))
    markup.add(types.InlineKeyboardButton("📝 Скачать субтитры", callback_data="download_subs"))
    ab = sorted({int(f.get('abr', 0)) for f in fmt_list if f.get('acodec') != 'none' and f.get('abr')}, reverse=True)
    for abr in ab:
        key = f"audio_{abr}k"
        txt = f"🔊{abr}k" + ("✅" if key in selected else "")
        markup.add(types.InlineKeyboardButton(txt, callback_data=f"toggle_{key}"))
    markup.add(
        types.InlineKeyboardButton("📅 Скачать", callback_data="download_selected"),
        types.InlineKeyboardButton(TEXT_CANCEL, callback_data="cancel_download")
    )
    return markup

def make_subtitles_buttons(subs: dict) -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup(row_width=2)
    for lang in subs.keys():
        markup.add(types.InlineKeyboardButton(f"🌐 {lang}", callback_data=f"sub_lang_{lang}"))
    markup.add(
        types.InlineKeyboardButton("🥒 Скачать с таймкодом", callback_data="sub_timed"),
        types.InlineKeyboardButton(TEXT_CANCEL, callback_data="cancel_download")
    )
    return markup

def update_progress_message_loop(chat_id, message_id, user_id):
    while True:
        time.sleep(1)
        lines = []
        finished = True
        for fname, percent in download_progress.get(user_id, {}).items():
            lines.append(f"{fname}: {percent}%")
            if percent < 100:
                finished = False
        text = "⬇️ Прогресс скачивания:\n" + ("\n".join(lines) if lines else "(ожидание)")
        try:
            bot.edit_message_text(text, chat_id, message_id)
        except:
            pass
        if finished:
            break

def download_with_progress(url, opts, chat_id, user_id, filename):
    def hook(d):
        status = d.get('status')
        if status == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 1
            downloaded = d.get('downloaded_bytes', 0)
            pct = int(downloaded / total * 100)
            download_progress.setdefault(user_id, {})[filename] = pct
        elif status == 'finished':
            download_progress.setdefault(user_id, {})[filename] = 100
    opts['progress_hooks'] = [hook]
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])
    download_progress.setdefault(user_id, {})[filename] = 100

def download_selected_formats(url: str, title: str, selected: set, chat_id, user_id):
    out_files = []
    download_progress.setdefault(user_id, {})
    for key in selected:
        if key.startswith("video_"):
            q = key.split("_")[1]
            out_path = os.path.join(BASE_TEMP_FOLDER, safe_filename(title) + f"_{q}p.mp4")
            opts = {'format': f"bestvideo[height={q}]+bestaudio/best", 'outtmpl': out_path, 'merge_output_format':'mp4','quiet':True,'noplaylist':True}
            fname = os.path.basename(out_path)
        else:
            abr = key.split("_")[1].rstrip('k')
            base = os.path.join(BASE_TEMP_FOLDER, safe_filename(title) + f"_{abr}k")
            opts = {'format':'bestaudio','outtmpl':base,'postprocessors':[{'key':'FFmpegExtractAudio','preferredcodec':'mp3','preferredquality':abr}],'quiet':True,'noplaylist':True}
            fname = os.path.basename(base) + ".mp3"
            out_path = base + ".mp3"
        download_progress[user_id][fname] = 0
        download_with_progress(url, opts, chat_id, user_id, fname)
        out_files.append(out_path)
    return out_files

def download_subtitles_info(url: str) -> dict:
    with yt_dlp.YoutubeDL({'quiet':True,'skip_download':True}) as ydl:
        info = ydl.extract_info(url, download=False)
    return {
        **info.get('subtitles', {}),
        **info.get('automatic_captions', {})
    }

def download_subtitle_file(url: str, lang: str, title: str, chat_id: int, timed: bool=False):
    base = os.path.join(BASE_TEMP_FOLDER, safe_filename(title) + f"_{lang}")
    vtt = base + ".vtt"
    opts = {'writesubtitles':True,'writeautomaticsub':True,'subtitleslangs':[lang],'subtitlesformat':'vtt','skip_download':True,'outtmpl':base,'quiet':True,'noplaylist':True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])
    if not os.path.exists(vtt):
        bot.send_message(chat_id, "⚠️ Субтитры не найдены.")
        return
    if timed:
        txt = base + "_timed.txt"
        with open(vtt, 'r', encoding='utf-8') as vf, open(txt, 'w', encoding='utf-8') as tf:
            for line in vf:
                if "-->" in line or (line.strip() and not line.strip().isdigit()):
                    tf.write(line)
        with open(txt, 'rb') as f:
            bot.send_document(chat_id, f, caption=f"🥒 Субтитры с таймкодом ({lang}) для {title}")
        os.remove(txt)
        os.remove(vtt)
    else:
        with open(vtt, 'rb') as f:
            bot.send_document(chat_id, f, caption=f"📝 Субтитры ({lang}) для {title}")
        os.remove(vtt)

@bot.message_handler(commands=['start'])
def cmd_start(message):
    bot.reply_to(message, TEXT_START)

@bot.message_handler(func=lambda m: m.text and (m.text.startswith("http") or (urlparse(m.text).hostname and urlparse(m.text).hostname.endswith("tiktok.com"))))
def handle_link(message):
    uid = message.from_user.id
    chat = message.chat.id
    user_links[uid] = message.text.strip()
    user_selected_formats[uid] = set()
    bot.send_message(chat, TEXT_ANALYZING)
    try:
        info = get_info(user_links[uid])
    except Exception as e:
        bot.reply_to(message, f"⚠️ Ошибка при получении информации:\n```{e}```", parse_mode="Markdown")
        return
    user_info[uid] = info
    title = info.get('title', 'Без названия')
    bot.send_message(
        chat,
        f"📋 *{title}*\nВыбери форматы для скачивания:",
        parse_mode="Markdown",
        reply_markup=make_format_buttons(info)
    )

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    uid = call.from_user.id
    chat = call.message.chat.id
    data = call.data
    info = user_info.get(uid)
    if not info:
        bot.send_message(chat, TEXT_FIRST_SEND_LINK)
        return
    sel = user_selected_formats.setdefault(uid, set())
    if data == "cancel_download":
        for d in (user_links, user_info, user_selected_formats, download_progress, user_subtitles_info):
            d.pop( uid, None)
        bot.edit_message_text(TEXT_CANCELLED, chat, call.message.message_id)
        return
    if data == "download_subs":
        subs = download_subtitles_info(user_links[uid])
        if not subs:
            bot.send_message(chat, "⚠️ Субтитры не найдены.")
            return
        user_subtitles_info[uid] = subs
        bot.edit_message_text(
            "🌐 Выберите язык субтитров или режим с таймкодом:",
            chat,
            call.message.message_id,
            reply_markup=make_subtitles_buttons(subs)
        )
        return
    if data.startswith("sub_lang_") or data == "sub_timed":
        lang = data.split("_")[-1] if data.startswith("sub_lang_") else next(iter(user_subtitles_info.get(uid, {'en': None})))
        timed = data == "sub_timed"
        bot.send_message(
            chat,
            f"📝 Скачиваю субтитры ({'таймкодом' if timed else lang}) для *{info.get('title','')}*...",
            parse_mode="Markdown"
        )
        threading.Thread(
            target=download_subtitle_file,
            args=(user_links[uid], lang, info.get('title',''), chat, timed)
        ).start()
        return
    if data.startswith("toggle_"):
        key = data.replace("toggle_", "")
        if key in sel:
            sel.remove(key)
        else:
            sel.add(key)
        bot.edit_message_reply_markup(chat, call.message.message_id, reply_markup=make_format_buttons(info, sel))
        return
    if data == "download_selected":
        if not sel:
            bot.answer_callback_query(call.id, "⚠️ Выберите формат!")
            return
        title = info.get('title', '')
        msg = bot.send_message(chat, "⬇️ Прогресс скачивания:\n(ожидание)").message_id
        threading.Thread(target=update_progress_message_loop, args=(chat, msg, uid)).start()
        def job():
            files = download_selected_formats(user_links[uid], title, sel, chat, uid)
            while any(p < 100 for p in download_progress.get(uid, {}).values()):
                time.sleep(1)
            for fpath in files:
                if os.path.exists(fpath):
                    with open(fpath, 'rb') as r:
                        if fpath.endswith('.mp4'):
                            bot.send_video(chat, r, caption=f"🎥 {title}")
                        else:
                            bot.send_audio(chat, r, caption=f"🔊 {title}")
                    os.remove(fpath)
                else:
                    bot.send_message(chat, f"⚠️ {os.path.basename(fpath)} не найден.")
            try:
                bot.delete_message(chat, msg)
            except:
                pass
            bot.send_message(chat, "✅ Готово! Отправьте новую ссылку.")
            for d in (user_links, user_info, user_selected_formats, download_progress, user_subtitles_info):
                d.pop(uid, None)
        threading.Thread(target=job).start()

bot.polling()
