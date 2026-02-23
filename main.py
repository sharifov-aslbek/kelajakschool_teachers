import asyncio
import logging
import gc
import calendar
import html
from datetime import datetime, timedelta, timezone
from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import (Message, CallbackQuery, ReplyKeyboardMarkup,
                           KeyboardButton, ReplyKeyboardRemove)
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ================= KONFIGURATSIYA =================
BOT_TOKEN = "8514239580:AAGD9c3Sls4WGwLmjf3xYhN8pXFTpifNuGU"
ADMIN_GROUP_ID = -1003799360830
TEACHER_PASSWORD = "12345"
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB limit

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()
dp.include_router(router)

# ================= HOLATLAR (FSM) =================
class TeacherReport(StatesGroup):
    waiting_for_contact = State()
    waiting_for_password = State()
    choosing_start_date = State()
    choosing_end_date = State()
    waiting_for_fullname = State()
    waiting_for_subject = State()

    # --- YANI HOLATLAR (Interactive Plan o'rniga) ---
    choosing_report_week = State()
    waiting_for_weekly_hours = State()
    choosing_day_of_week = State()
    waiting_for_day_hours = State()
    waiting_for_lesson_topic = State()
    waiting_for_lesson_homework = State()
    # -----------------------------------------------

    waiting_for_test_sample = State()
    waiting_for_test_results = State()

# ================= YORDAMCHI FUNKSIYALAR =================
def get_contact_kb():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Raqamni ulashish", request_contact=True)]],
        resize_keyboard=True, one_time_keyboard=True
    )

def get_calendar_kb(prefix: str, month_offset=0):
    builder = InlineKeyboardBuilder()
    now = datetime.now()
    target_month = (now.month + month_offset - 1) % 12 + 1
    target_year = now.year + (now.month + month_offset - 1) // 12

    for day in range(1, 32):
        try:
            date_str = f"{target_year}-{target_month:02d}-{day:02d}"
            datetime.strptime(date_str, "%Y-%m-%d")
            builder.button(text=str(day), callback_data=f"cal:{prefix}:{date_str}")
        except ValueError:
            continue

    builder.adjust(7)
    return builder.as_markup()

def get_last_week_range():
    today = datetime.now()
    days_to_last_monday = today.weekday() + 7
    last_monday = today - timedelta(days=days_to_last_monday)
    last_sunday = last_monday + timedelta(days=6)
    return f"{last_monday.strftime('%d.%m.%Y')} - {last_sunday.strftime('%d.%m.%Y')}"

def get_month_weeks_kb():
    # UTC+5 (Asia/Tashkent) fallback if zoneinfo is not imported
    tz = timezone(timedelta(hours=5))
    now = datetime.now(tz)
    year = now.year
    month = now.month

    _, last_day = calendar.monthrange(year, month)

    months_uz = ["yanvar", "fevral", "mart", "aprel", "may", "iyun",
                 "iyul", "avgust", "sentyabr", "oktyabr", "noyabr", "dekabr"]
    m_name = months_uz[month - 1]

    builder = InlineKeyboardBuilder()

    w1 = f"1-hafta: 01-{m_name}dan 07-{m_name}gacha"
    w2 = f"2-hafta: 08-{m_name}dan 14-{m_name}gacha"
    w3 = f"3-hafta: 15-{m_name}dan 21-{m_name}gacha"
    w4 = f"4-hafta: 22-{m_name}dan {last_day}-{m_name}gacha"

    builder.button(text=w1, callback_data="repweek:1")
    builder.button(text=w2, callback_data="repweek:2")
    builder.button(text=w3, callback_data="repweek:3")
    builder.button(text=w4, callback_data="repweek:4")

    builder.adjust(1)

    weeks_map = {
        "repweek:1": w1, "repweek:2": w2, "repweek:3": w3, "repweek:4": w4
    }
    return builder.as_markup(), weeks_map

async def show_day_selection(event, state: FSMContext):
    await state.set_state(TeacherReport.choosing_day_of_week)
    builder = InlineKeyboardBuilder()
    days = ["Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba"]
    for d in days:
        builder.button(text=d, callback_data=f"selday:{d}")

    # To exit cycle and move to next file upload steps
    builder.button(text="Davom etish ➡️", callback_data="selday:done")
    builder.adjust(2, 2, 2, 1)

    text = "Kunni tanlang (barcha kunlarni kiritib bo'lgach 'Davom etish ➡️' tugmasini bosing):"

    if isinstance(event, Message):
        await event.answer(text, reply_markup=builder.as_markup())
    else:
        await event.message.answer(text, reply_markup=builder.as_markup())
        await event.answer()

# ================= HANDLERLAR =================

@router.message(Command("cancel"))
@router.message(F.text.lower() == "bekor qilish")
async def cmd_cancel(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        return
    await state.clear()
    gc.collect()
    await message.answer(
        "❌ Barcha amallar bekor qilindi va xotira tozalandi. Boshidan boshlash uchun /start bosing.",
        reply_markup=ReplyKeyboardRemove()
    )

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(TeacherReport.waiting_for_contact)
    await message.answer(
        "Assalomu alaykum! Boshlash uchun pastdagi tugma orqali telefon raqamingizni yuboring.\n\n"
        "<i>(Jarayonni to'xtatish uchun /cancel ni bosing)</i>",
        reply_markup=get_contact_kb(),
        parse_mode="HTML"
    )

@router.message(TeacherReport.waiting_for_contact)
async def process_contact(message: Message, state: FSMContext):
    if message.contact:
        await state.update_data(phone=message.contact.phone_number)
        await state.set_state(TeacherReport.waiting_for_password)
        await message.answer("✅ Raqamingiz saqlandi. Endi o'qituvchi parolini kiriting:", reply_markup=ReplyKeyboardRemove())
    else:
        await message.answer("⚠️ Iltimos, pastdagi '📱 Raqamni ulashish' tugmasini bosing.")

@router.message(TeacherReport.waiting_for_password)
async def process_password(message: Message, state: FSMContext):
    if message.text == TEACHER_PASSWORD:
        await state.set_state(TeacherReport.choosing_start_date)
        await message.answer("✅ Parol to'g'ri. Hisobotning BOSHLANISH sanasini tanlang:", reply_markup=get_calendar_kb("start"))
    else:
        await message.answer("❌ Parol noto'g'ri. Iltimos, qaytadan urinib ko'ring:")

@router.callback_query(F.data.startswith("cal:"))
async def handle_calendar(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    prefix, date_val = parts[1], parts[2]

    if prefix == "start":
        await state.update_data(start_date=date_val)
        await state.set_state(TeacherReport.choosing_end_date)
        await callback.message.edit_text(f"Boshlanish sanasi: {date_val}\nEndi TUGASH sanasini tanlang:", reply_markup=get_calendar_kb("end"))
    else:
        data = await state.get_data()
        start_dt = datetime.strptime(data['start_date'], "%Y-%m-%d")
        end_dt = datetime.strptime(date_val, "%Y-%m-%d")
        range_str = f"{start_dt.strftime('%d.%m.%Y')} - {end_dt.strftime('%d.%m.%Y')}"
        await state.update_data(date_range=range_str)
        await state.set_state(TeacherReport.waiting_for_fullname)
        await callback.message.answer(f"📅 Sana oralig'i: {range_str}\n\nIsm va familiyangizni kiriting:")
        await callback.answer()

@router.message(TeacherReport.waiting_for_fullname)
async def process_name(message: Message, state: FSMContext):
    await state.update_data(fullname=message.text)
    await state.set_state(TeacherReport.waiting_for_subject)
    await message.answer("Qaysi fan bo'yicha dars berasiz?")

# --- MODIFIED: Transitioning to the new Plan Logic ---
@router.message(TeacherReport.waiting_for_subject)
async def process_subject(message: Message, state: FSMContext):
    await state.update_data(subject=message.text)

    # Switch to week selection instead of file upload
    await state.set_state(TeacherReport.choosing_report_week)
    kb, weeks_dict = get_month_weeks_kb()
    await state.update_data(weeks_dict=weeks_dict)

    await message.answer("Oyning qaysi haftasi uchun hisobot kiritmoqchisiz?", reply_markup=kb)

@router.callback_query(TeacherReport.choosing_report_week, F.data.startswith("repweek:"))
async def process_report_week(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    weeks_dict = data.get("weeks_dict", {})
    selected_week = weeks_dict.get(callback.data, "Noma'lum hafta")

    await state.update_data(report_week_range=selected_week)
    await state.set_state(TeacherReport.waiting_for_weekly_hours)

    await callback.message.edit_text(
        f"✅ <b>{selected_week}</b> tanlandi.\n\n"
        "Bu hafta uchun necha soat darsingiz bor?",
        parse_mode="HTML"
    )

@router.message(TeacherReport.waiting_for_weekly_hours)
async def process_weekly_hours(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("⚠️ Iltimos, faqat raqam kiriting. Bu hafta uchun necha soat darsingiz bor?")
        return

    await state.update_data(weekly_hours=int(message.text), lessons_data={})
    await show_day_selection(message, state)

@router.callback_query(TeacherReport.choosing_day_of_week, F.data.startswith("selday:"))
async def process_day_selection(callback: CallbackQuery, state: FSMContext):
    day = callback.data.split(":")[1]

    if day == "done":
        # Cycle finished -> Proceed to normal file uploads
        await state.set_state(TeacherReport.waiting_for_test_sample)
        await callback.message.edit_text(
            "📄 O'tgan hafta test namunasi faylini yuklang:\n*(Maksimal hajm: 10 MB)*",
            parse_mode="Markdown"
        )
        return

    await state.update_data(current_day=day)
    await state.set_state(TeacherReport.waiting_for_day_hours)

    builder = InlineKeyboardBuilder()
    builder.button(text="Bu kunda darsim yo‘q", callback_data=f"skipday:{day}")

    await callback.message.edit_text(
        f"<b>{day}</b> kunda necha soat dars o‘tasiz?",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )

@router.message(TeacherReport.waiting_for_day_hours)
async def process_day_hours_msg(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("⚠️ Iltimos, faqat raqam kiriting. Necha soat dars o'tasiz?")
        return
    await handle_day_hours(int(message.text), message, state)

@router.callback_query(TeacherReport.waiting_for_day_hours, F.data.startswith("skipday:"))
async def process_skip_day(callback: CallbackQuery, state: FSMContext):
    await handle_day_hours(0, callback, state)

async def handle_day_hours(hours: int, event, state: FSMContext):
    if hours <= 0:
        # Move back to day selection directly
        await show_day_selection(event, state)
        return

    await state.update_data(target_lessons=hours, current_lesson_num=1)
    data = await state.get_data()
    day = data['current_day']

    # Initialize this day's list in state dictionary
    lessons_data = data.get('lessons_data', {})
    lessons_data[day] = []
    await state.update_data(lessons_data=lessons_data)

    await state.set_state(TeacherReport.waiting_for_lesson_topic)
    msg_text = f"<b>{day}</b>. 1-dars mavzusi nima bo‘ldi?"

    if isinstance(event, Message):
        await event.answer(msg_text, parse_mode="HTML")
    else:
        await event.message.edit_text(msg_text, parse_mode="HTML")

@router.message(TeacherReport.waiting_for_lesson_topic)
async def process_lesson_topic(message: Message, state: FSMContext):
    await state.update_data(temp_topic=message.text)
    data = await state.get_data()
    c_num = data['current_lesson_num']

    await state.set_state(TeacherReport.waiting_for_lesson_homework)
    await message.answer(f"{c_num}-dars uchun uyga vazifa nima berildi?")

@router.message(TeacherReport.waiting_for_lesson_homework)
async def process_lesson_homework(message: Message, state: FSMContext):
    data = await state.get_data()
    day = data['current_day']
    c_num = data['current_lesson_num']
    t_less = data['target_lessons']
    topic = data['temp_topic']
    homework = message.text

    # Append to state
    lessons_data = data.get('lessons_data', {})
    lessons_data[day].append({"topic": topic, "homework": homework})
    await state.update_data(lessons_data=lessons_data)

    if c_num < t_less:
        # Next lesson for the same day
        c_num += 1
        await state.update_data(current_lesson_num=c_num)
        await state.set_state(TeacherReport.waiting_for_lesson_topic)
        await message.answer(f"<b>{day}</b>. {c_num}-dars mavzusi nima bo‘ldi?", parse_mode="HTML")
    else:
        # Cycle complete for this day, prompt the day menu again
        await show_day_selection(message, state)
# --- END MODIFIED PLAN LOGIC ---

@router.message(TeacherReport.waiting_for_test_sample, F.document)
async def process_sample(message: Message, state: FSMContext):
    if message.document.file_size > MAX_FILE_SIZE:
        await message.answer("⚠️ Fayl hajmi 10 MB dan oshmasligi kerak. Iltimos, kichikroq fayl yuklang:")
        return
    await state.update_data(test_sample_id=message.document.file_id)
    await state.set_state(TeacherReport.waiting_for_test_results)
    await message.answer("📄 O'tgan hafta test natijalari faylini yuklang:\n*(Maksimal hajm: 10 MB)*", parse_mode="Markdown")

@router.message(TeacherReport.waiting_for_test_results, F.document)
async def process_final(message: Message, state: FSMContext):
    if message.document.file_size > MAX_FILE_SIZE:
        await message.answer("⚠️ Fayl hajmi 10 MB dan oshmasligi kerak. Iltimos, kichikroq fayl yuklang:")
        return

    data = await state.get_data()
    test_results_id = message.document.file_id

    # Base details
    phone = data.get('phone', "Noma'lum")
    date_range = data.get('date_range', "Noma'lum")
    fullname = html.escape(data.get('fullname', "Noma'lum"))
    subject = html.escape(data.get('subject', "Noma'lum"))

    # New Plan Details
    report_week_range = data.get('report_week_range', "Noma'lum")
    weekly_hours = data.get('weekly_hours', 0)
    lessons_data = data.get('lessons_data', {})

    report_text = (
        "📊 <b>YANGI HAFTALIK HISOBOT</b>\n\n"
        f"📱 <b>Telefon:</b> {phone}\n"
        f"🗓 <b>Sana oralig'i:</b> {date_range}\n"
        f"👤 <b>O'qituvchi:</b> {fullname}\n"
        f"📚 <b>Fan:</b> {subject}\n"
        f"📅 <b>Tanlangan hafta:</b> {report_week_range}\n"
        f"⏰ <b>Haftalik umumiy soat:</b> {weekly_hours}\n\n"
        "📝 <b>Kunlik darslar:</b>\n"
    )

    if not lessons_data:
        report_text += "<i>Ma'lumot kiritilmagan.</i>\n"
    else:
        for d_name, l_list in lessons_data.items():
            if not l_list:
                continue
            report_text += f"\n🔹 <b>{d_name} ({len(l_list)} soat):</b>\n"
            for i, lesson in enumerate(l_list, start=1):
                safe_topic = html.escape(lesson['topic'])
                safe_homework = html.escape(lesson['homework'])
                report_text += f"  {i}. <i>Mavzu:</i> {safe_topic}\n"
                report_text += f"     <i>Vazifa:</i> {safe_homework}\n"

    try:
        await bot.send_message(ADMIN_GROUP_ID, report_text, parse_mode="HTML")

        last_week_dates = get_last_week_range()
        last_week_sig = f"({fullname}) ({last_week_dates})"

        # Note: 'plan_file_id' document is no longer sent since we replaced it
        await bot.send_document(ADMIN_GROUP_ID, data['test_sample_id'], caption=f"📄 O'tgan hafta test namunasi {last_week_sig}")
        await bot.send_document(ADMIN_GROUP_ID, test_results_id, caption=f"📈 O'tgan hafta test natijalari {last_week_sig}")

        await message.answer("✅ Ma'lumotlaringiz muvaffaqiyatli yuborildi. Rahmat!")
    except Exception as e:
        logging.error(f"Xatolik: {e}")
        await message.answer("❌ Xatolik yuz berdi. Bot admin guruhga yozolmayapti.")

    finally:
        await state.clear()
        gc.collect()

async def main():
    print("Bot ishga tushdi...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())