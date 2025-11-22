import os
import logging
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters
from pydub import AudioSegment
import speech_recognition as sr
import google.generativeai as genai

# --- تنظیمات ---
TELEGRAM_BOT_TOKEN = ""
GEMINI_API_KEY = ""

current_dir = os.getcwd()

AudioSegment.converter = os.path.join(current_dir, "ffmpeg.exe")
AudioSegment.ffprobe = os.path.join(current_dir, "ffprobe.exe")

# تنظیمات Gemini
genai.configure(api_key=GEMINI_API_KEY)
# مدل Flash سرعت بالا و هزینه کمی دارد (در نسخه رایگان محدودیت دارد اما برای تست عالی است)
model = genai.GenerativeModel('gemini-2.5-flash')

# تنظیم لاگ
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

async def convert_voice_to_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    status_msg = await update.message.reply_text("📥 در حال دریافت صدا...")
    
    # نام فایل‌ها
    ogg_path = f"voice_{user_id}.ogg"
    mp3_path = f"voice_{user_id}.mp3" # جمینای MP3 را خوب می‌فهمد
    wav_path = f"voice_{user_id}.wav" # SpeechRecognition به WAV نیاز دارد

    try:
        # 1. دانلود فایل
        new_file = await update.message.effective_attachment.get_file()
        await new_file.download_to_drive(ogg_path)

        # تبدیل صدا برای پردازش
        audio = AudioSegment.from_ogg(ogg_path)
        
        text_result = ""
        method_used = ""
        is_success = False

        await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=status_msg.message_id, text="🤖 در حال پردازش با Gemini...")

        # --- تلاش اول: استفاده از هوش مصنوعی Gemini ---
        try:
            # تبدیل به MP3 برای جمینای (حجم کمتر، کیفیت خوب)
            audio.export(mp3_path, format="mp3")
            
            # آپلود فایل به سرورهای گوگل (جمینای برای فایل‌های صوتی نیاز به آپلود دارد)
            uploaded_file = genai.upload_file(mp3_path, mime_type="audio/mp3")
            
            # درخواست از هوش مصنوعی
            prompt = "فایل صوتی زیر را دقیقاً به متن فارسی تبدیل کن. هیچ توضیح اضافه‌ای نده، فقط متن گفته شده را بنویس."
            response = model.generate_content([prompt, uploaded_file])
            
            text_result = response.text
            method_used = "✨ هوش مصنوعی Google Gemini 2.5"
            is_success = True
            
            # حذف فایل از سرور گوگل برای رعایت حریم خصوصی و فضا
            uploaded_file.delete()

        except Exception as e:
            logging.error(f"Gemini Error: {e}")
            # --- تلاش دوم: روش جایگزین (Google Speech Recognition) ---
            await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=status_msg.message_id, text="⚠️ جمینای پاسخ نداد، سوییچ به موتور کلاسیک...")
            
            try:
                # تبدیل به WAV برای کتابخانه SpeechRecognition
                audio.export(wav_path, format="wav")
                
                recognizer = sr.Recognizer()
                with sr.AudioFile(wav_path) as source:
                    audio_data = recognizer.record(source)
                    # استفاده از API رایگان گوگل
                    text_result = recognizer.recognize_google(audio_data, language="fa-IR")
                    method_used = "🌐 موتور تشخیص گفتار گوگل (روش جایگزین)"
                    is_success = True
            except Exception as e_fallback:
                logging.error(f"Fallback Error: {e_fallback}")

        # ارسال نتیجه
        if is_success and text_result:
            final_text = f"📝 **متن:**\n{text_result}\n\n⚙️ *پردازش:* {method_used}"
            await update.message.reply_text(final_text, parse_mode="Markdown")
        else:
            await update.message.reply_text("❌ خطا: نتوانستم صدا را به متن تبدیل کنم.")

    except Exception as e:
        logging.error(f"General Error: {e}")
        await update.message.reply_text("❌ خطایی در دریافت یا تبدیل فایل رخ داد.")

    finally:
        # پاکسازی فایل‌های موقت از سرور شما
        await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=status_msg.message_id)
        for path in [ogg_path, mp3_path, wav_path]:
            if os.path.exists(path):
                os.remove(path)

if __name__ == '__main__':
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # هندلر برای دریافت ویس و فایل صوتی
    voice_handler = MessageHandler(filters.VOICE | filters.AUDIO, convert_voice_to_text)
    application.add_handler(voice_handler)

    print("Gemini Voice Bot is running...")
    application.run_polling()