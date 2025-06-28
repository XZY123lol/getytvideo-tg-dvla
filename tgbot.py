import telebot
from pytube import YouTube
from telegram import Update
from telegram.ext import CommandHandler, CallbackContext
from tqdm import tqdm
import time
import requests
import random

print("Запуск...")
for _ in tqdm(range(100), desc="Запуск бота", unit="%", dynamic_ncols=True):
    time.sleep(0.1)  # Имитация работы

#Токен
TOKEN = 'Токен_сюда_вставь'

bot = telebot.TeleBot(TOKEN)

#/start
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "Привет! Отправь мне ссылку на видео на YouTube, и я отправлю его тебе")

@bot.message_handler(commands=['help'])
def send_welcome(message):
    bot.reply_to(message, "/start - Запуск бота\n/help - Показывает все команды бота\n/errors - показывает список ошибок которые могут произойти")

@bot.message_handler(commands=['errors'])
def send_welcome(message):
    bot.reply_to(message, "regex_search: could not find match for (?:v=|\/)([0-9A-Za-z_-]{11}).* - Эта ошибка указывает на то что вы вели неконкретный запрос,другую сыллку или написали какое-то слово\nПока на этом все ошибки но попытаюсь найти больше!")

def download_file(url, filename, desc="Скачивание файла", unit="B", chunk_size=1024):
    response = requests.get(url, stream=True)
    total_size = int(response.headers.get('content-length', 0))
    
    with open(filename, 'wb') as file, tqdm(
        desc=desc,
        total=total_size,
        unit=unit,
        unit_scale=True,
        dynamic_ncols=True
    ) as progress_bar:
        for data in response.iter_content(chunk_size=chunk_size):
            progress_bar.update(len(data))
            file.write(data)

@bot.message_handler(func=lambda message: True)
def download_video(message):
    try:
        bot.reply_to(message, 'Скачивание видео подождите чуть-чуть...')
        video_url = message.text
        yt = YouTube(video_url)
        video = yt.streams.get_highest_resolution()
        audio = yt.streams.get_audio_only()
        bot.reply_to(message, 'Создаем файлы...')

        download_file(video.url, 'video.mp4', "Скачивание видео")
        download_file(audio.url, 'audio.mp3', "Скачивание аудио")

        bot.reply_to(message, 'Отправка...')
        bot.send_video(message.chat.id, open('video.mp4', 'rb'))
        bot.send_audio(message.chat.id, open('audio.mp3', 'rb'))

    except Exception as e:
        # Выводим инфу об ошибке в консоль
        print(f"Произошла ошибка у пользователя с ID {message.from_user.id} ({message.from_user.username}): {str(e)}")

        # Сообщение об ошибке
        bot.reply_to(message, f"Произошла ошибка: {str(e)}. Эта ошибка предоставлена в консоль если хотите рассказать об этом по подробней то обращайтесь мне.\nВы можете посмотреть список ошибок в /errors так что вы можете не беспокоится")
        
bot.polling()
