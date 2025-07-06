import telebot
from telebot import types
import yt_dlp
import os
import tempfile
import shutil

print("Запуск...")

TOKEN = 'тг_бот_токен'
bot = telebot.TeleBot(TOKEN)
user_links = {}
user_info = {}

def get_info(url):
    with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
        return ydl.extract_info(url, download=False)

def safe_filename(name):
    return "".join(c for c in name if c.isalnum() or c in " .-_").rstrip()

def download_video(url, title, format_str="bestvideo+bestaudio", folder=None):
    folder = folder or tempfile.mkdtemp()
    filename = safe_filename(title) + ".mp4"
    path = os.path.join(folder, filename)
    opts = {
        'format': format_str,
        'outtmpl': path,
        'merge_output_format': 'mp4',
        'quiet': True,
        'writesubtitles': False,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])
    return path, folder

def download_audio(url, title, bitrate="128k", folder=None):
    folder = folder or tempfile.mkdtemp()
    filename = safe_filename(title) + ".mp3"
    path = os.path.join(folder, filename)
    opts = {
        'format': 'bestaudio',
        'outtmpl': path,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': bitrate.replace('k', '')
        }],
        'quiet': True,
        'writesubtitles': False,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])
    return path, folder

def download_subtitles(url, title, lang='en', folder=None):
    folder = folder or tempfile.mkdtemp()
    filename = safe_filename(title) + ".srt"
    path = os.path.join(folder, filename)
    opts = {
        'writesubtitles': True,
        'subtitleslangs': [lang],
        'skip_download': True,
        'outtmpl': path,
        'quiet': True,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
        if os.path.exists(path):
            return path, folder
        else:
            return None, folder
    except Exception:
        return None, folder

def get_thumbnail_url(info):
    thumbs = info.get('thumbnails')
    if thumbs:
        return thumbs[-1]['url']
    return None

def download_thumbnail(url):
    import requests
    try:
        resp = requests.get(url, stream=True, timeout=10)
        if resp.status_code == 200:
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
            with open(tmp.name, 'wb') as f:
                for chunk in resp.iter_content(1024):
                    f.write(chunk)
            return tmp.name
    except Exception:
        return None

@bot.message_handler(commands=['start'])
def start_command(message):
    bot.reply_to(message, "Привет! Отправь ссылку на YouTube (или плейлист), я покажу доступные форматы.")

@bot.message_handler(commands=['help'])
def help_command(message):
    bot.reply_to(message, "/start — перезапуск\n/help — справка\n/errors — список ошибок")

@bot.message_handler(func=lambda m: m.text and m.text.startswith("http"))
def handle_link(message):
    url = message.text
    user_links[message.from_user.id] = url

    try:
        info = get_info(url)
    except Exception as e:
        bot.reply_to(message, f"Ошибка при получении информации: {e}")
        return

    user_info[message.from_user.id] = info
    title = info.get('title', 'Без названия')

    if info.get('_type') == 'playlist':
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("📥 Скачать весь плейлист", callback_data="download_playlist"))
        markup.add(types.InlineKeyboardButton("❌ Отмена", callback_data="cancel_download"))
        bot.reply_to(message, f"Это плейлист с {len(info.get('entries', []))} видео.\nВыберите действие:", reply_markup=markup)
        return

    video_qualities = sorted(set(f['height'] for f in info['formats'] if f.get('vcodec') != 'none' and f.get('height')))
    audio_bitrates = sorted(set(int(f.get('abr')) for f in info['formats'] if f.get('acodec') != 'none' and f.get('abr')), reverse=True)
    subtitles_available = bool(info.get('subtitles'))

    markup = types.InlineKeyboardMarkup(row_width=2)

    for height in video_qualities:
        markup.add(types.InlineKeyboardButton(f"🎥 {height}p", callback_data=f"video_{height}"))

    for abr in audio_bitrates:
        markup.add(types.InlineKeyboardButton(f"🔊 {abr}k", callback_data=f"audio_{abr}k"))

    if subtitles_available:
        markup.add(types.InlineKeyboardButton("📝 Скачать субтитры", callback_data="download_subtitles"))

    markup.add(
        types.InlineKeyboardButton("📥 Всё (макс)", callback_data="all_best"),
        types.InlineKeyboardButton("❌ Отмена", callback_data="cancel_download")
    )

    bot.reply_to(message, f"🎬 *{title}*\nВыбери формат для загрузки:", parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    url = user_links.get(user_id)
    info = user_info.get(user_id)

    if call.data == "cancel_download":
        bot.send_message(chat_id, "🚫 Отменено. Отправьте новую ссылку.")
        user_links.pop(user_id, None)
        user_info.pop(user_id, None)
        return

    if not url or not info:
        bot.send_message(chat_id, "Сначала отправьте ссылку на YouTube.")
        return

    title = info.get('title', 'Без названия')

    try:
        if call.data.startswith("video_"):
            quality = call.data.split("_")[1]
            format_str = f"bestvideo[height={quality}]+bestaudio/best"
            bot.send_message(chat_id, f"⏳ Скачиваем видео {quality}p...")
            path, folder = download_video(url, title, format_str)
            thumb_url = get_thumbnail_url(info)
            thumb_path = download_thumbnail(thumb_url) if thumb_url else None
            with open(path, 'rb') as vid:
                if thumb_path:
                    with open(thumb_path, 'rb') as thumb:
                        bot.send_video(chat_id, vid, caption=f"🎥 {title} ({quality}p)", thumb=thumb)
                    os.remove(thumb_path)
                else:
                    bot.send_video(chat_id, vid, caption=f"🎥 {title} ({quality}p)")
            shutil.rmtree(folder)

        elif call.data.startswith("audio_"):
            abr = call.data.split("_")[1]
            bot.send_message(chat_id, f"⏳ Скачиваем аудио {abr}...")
            path, folder = download_audio(url, title, abr)
            thumb_url = get_thumbnail_url(info)
            thumb_path = download_thumbnail(thumb_url) if thumb_url else None
            with open(path, 'rb') as aud:
                if thumb_path:
                    with open(thumb_path, 'rb') as thumb:
                        bot.send_audio(chat_id, aud, caption=f"🔊 {title} ({abr})", thumb=thumb)
                    os.remove(thumb_path)
                else:
                    bot.send_audio(chat_id, aud, caption=f"🔊 {title} ({abr})")
            shutil.rmtree(folder)

        elif call.data == "download_subtitles":
            bot.send_message(chat_id, "⏳ Скачиваем субтитры...")
            path, folder = download_subtitles(url, title)
            if path:
                with open(path, 'rb') as sub:
                    bot.send_document(chat_id, sub, caption=f"📝 Субтитры: {title}")
                shutil.rmtree(folder)
            else:
                bot.send_message(chat_id, "Субтитры не найдены.")

        elif call.data == "all_best":
            bot.send_message(chat_id, f"⏳ Скачиваем всё в лучшем качестве: {title}")
            vpath, vfolder = download_video(url, title)
            apath, afolder = download_audio(url, title)
            thumb_url = get_thumbnail_url(info)
            thumb_path = download_thumbnail(thumb_url) if thumb_url else None
            with open(vpath, 'rb') as vid:
                if thumb_path:
                    with open(thumb_path, 'rb') as thumb:
                        bot.send_video(chat_id, vid, caption=f"🎥 {title} (HD)", thumb=thumb)
                    os.remove(thumb_path)
                else:
                    bot.send_video(chat_id, vid, caption=f"🎥 {title} (HD)")
            with open(apath, 'rb') as aud:
                if thumb_path is None:
                    bot.send_audio(chat_id, aud, caption=f"🔊 {title}")
                # если превью уже удалили - отправим без него
                else:
                    bot.send_audio(chat_id, aud, caption=f"🔊 {title}")
            shutil.rmtree(vfolder)
            shutil.rmtree(afolder)

        elif call.data == "download_playlist":
            bot.send_message(chat_id, "⏳ Скачиваем весь плейлист... Это может занять время.")
            folder = tempfile.mkdtemp()
            opts = {
                'outtmpl': os.path.join(folder, '%(playlist_index)s - %(title)s.%(ext)s'),
                'quiet': True,
                'ignoreerrors': True,
            }
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
            archive_path = os.path.join(folder, "playlist.zip")
            shutil.make_archive(os.path.splitext(archive_path)[0], 'zip', folder)
            with open(archive_path, 'rb') as archive:
                bot.send_document(chat_id, archive, caption=f"📥 Плейлист: {title}")
            shutil.rmtree(folder)

    except Exception as e:
        bot.send_message(chat_id, f"⚠️ Ошибка при скачивании: {e}")
        print(f"[{user_id}] Ошибка: {e}")

bot.polling()