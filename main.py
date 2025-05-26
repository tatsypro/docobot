from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, ConversationHandler
import requests
from bs4 import BeautifulSoup
import openai

TOKEN = 'YOUR_TELEGRAM_BOT_TOKEN'
openai.api_key = 'YOUR_OPENAI_API_KEY'

LINK, VERIFY, EDIT = range(3)

def start(update, context):
            update.message.reply_text("Привет! Отправь ссылку на сайт, и я подготовлю документы по 152-ФЗ.")
            return LINK

        def handle_link(update, context):
            text = update.message.text.strip()
            if "." not in text:
                return LINK
            url = text if text.startswith("http") else "https://" + text
            update.message.reply_text(f"🔍 Начинаю анализ сайта: {url}")
            try:
                r = requests.get(url, timeout=10)
                soup = BeautifulSoup(r.text, "html.parser")
                site_text = soup.get_text(separator="\n", strip=True)
                with open("prompt.txt", "r", encoding="utf-8") as f:
                    base_prompt = f.read()
                full_prompt = base_prompt.strip() + f"\n\n🧾 Текст сайта ({url}):\n\n" + site_text
                response = openai.ChatCompletion.create(
                    model="gpt-4o",
                    messages=[{"role": "user", "content": full_prompt}],
                    temperature=0.2,
                    max_tokens=2000
                )
                extracted = response.choices[0]["message"]["content"]
                update.message.reply_text("🔎 Вот данные, извлечённые с сайта:\n\n" + extracted)
                context.user_data["extracted"] = extracted
                keyboard = [["✅ Всё верно", "✏ Изменить"]]
                update.message.reply_text("Проверьте данные выше. Выберите действие:",
                    reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True))
                return VERIFY
            except Exception as e:
                update.message.reply_text(f"❌ Ошибка при анализе сайта:\n{e}")
                return LINK

        def handle_verification(update, context):
            text = update.message.text.lower()
            if "верно" in text:
                update.message.reply_text("✅ Отлично! Теперь давайте уточним недостающие данные.",
                    reply_markup=ReplyKeyboardRemove())
                extracted = context.user_data.get("extracted", "")
                prompt = (
                    f"Ты — эксперт по обработке персональных данных. На основе извлечённых с сайта переменных, сформулируй список вопросов пользователю.\n"
                    "Используй человекопонятные формулировки. Запрашивай поочередно, чтобы было удобно отвечать.\n\n"
                    "1. Сначала задай вопросы о недостающих переменных.\n"
                    "2. Затем юридические:\n"
                    "- Вы используете оферту, индивидуальный договор или не оказываете платные услуги?\n"
                    "- Срок оказания услуг\n"
                    "- Наличие тестового доступа\n"
                    "- Условия возврата\n"
                    "- Платёжная система\n"
                    "- География оказания услуг\n"
                    "- Способы сбора данных\n"
                    "- Трансграничная передача\n"
                    "- Особые условия (дети, реклама, подписки и т.п.)\n\n"
                    "Формулируй дружелюбно, не используй шаблонных фраз типа 'все поля обязательны'."
                    f"\n\nВот что уже известно:\n{extracted}"
                )
                try:
                    response = openai.ChatCompletion.create(
                        model="gpt-4o",
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.4,
                        max_tokens=1000
                    )
                    questions_raw = response.choices[0]["message"]["content"]
                    questions = [q.strip() for q in questions_raw.splitlines() if q.strip()]
                    context.user_data["questions"] = questions
                    context.user_data["answers"] = []
                    update.message.reply_text(f"✏ Уточним подробности. Вопрос 1 из {len(questions)}:\n\n{questions[0]}")
                    return EDIT
                except Exception as e:
                    update.message.reply_text(f"❌ Ошибка GPT:\n{e}")
                    return VERIFY
            elif "изменить" in text:
                update.message.reply_text("✍️ Введите правки в удобной форме:",
                    reply_markup=ReplyKeyboardRemove())
                context.user_data["awaiting_edit"] = True
                return EDIT
            return VERIFY

        def handle_edit(update, context):
            text = update.message.text.strip()
            if context.user_data.get("awaiting_edit"):
                context.user_data["manual_correction"] = text
                context.user_data["awaiting_edit"] = False
                update.message.reply_text("✅ Правки сохранены. Нажмите 'Всё верно' для продолжения.",
                    reply_markup=ReplyKeyboardMarkup([["✅ Всё верно", "✏ Изменить"]],
                        one_time_keyboard=True, resize_keyboard=True))
                return VERIFY
            answers = context.user_data.get("answers", [])
            questions = context.user_data.get("questions", [])
            answers.append(text)
            context.user_data["answers"] = answers
            if len(answers) < len(questions):
                next_q = questions[len(answers)]
                update.message.reply_text(f"Вопрос {len(answers)+1} из {len(questions)}:\n\n{next_q}")
                return EDIT
            extracted = context.user_data.get("extracted", "")
            user_answers = "\n".join(answers)
            manual_fix = context.user_data.get("manual_correction", "")
            final_prompt = (
                f"Ты — юридический помощник. На основе:\n"
                f"🔹 Данных с сайта:\n{extracted}\n\n"
                f"✏ Уточнений пользователя:\n{user_answers}\n\n"
                f"{'🛠 Правки:\n' + manual_fix if manual_fix else ''}\n"
                "Сгенерируй итоговый список переменных для юридических документов (152-ФЗ)."
            )
            try:
                response = openai.ChatCompletion.create(
                    model="gpt-4o",
                    messages=[{"role": "user", "content": final_prompt}],
                    temperature=0.3,
                    max_tokens=1800
                )
                result = response.choices[0]["message"]["content"]
                context.user_data["final_data"] = result
                update.message.reply_text("📄 Финальные данные собраны:")
                update.message.reply_text(result)
                return ConversationHandler.END
            except Exception as e:
                update.message.reply_text(f"❌ Ошибка генерации:\n{e}")
                return EDIT

        def main():
            updater = Updater(TOKEN, use_context=True)
            dp = updater.dispatcher
            conv = ConversationHandler(
                entry_points=[CommandHandler("start", start)],
                states={
                    LINK: [MessageHandler(Filters.text & ~Filters.command, handle_link)],
                    VERIFY: [MessageHandler(Filters.text & ~Filters.command, handle_verification)],
                    EDIT: [MessageHandler(Filters.text & ~Filters.command, handle_edit)],
                },
                fallbacks=[]
            )
            dp.add_handler(conv)
            updater.start_polling()
            updater.idle()

        if __name__ == '__main__':
            main()