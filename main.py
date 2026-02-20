import asyncio
import logging
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import (Message, CallbackQuery, ReplyKeyboardMarkup,
                           KeyboardButton, InlineKeyboardButton, ReplyKeyboardRemove)
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ================= KONFIGURATSIYA =================
BOT_TOKEN = "8514239580:AAGD9c3Sls4WGwLmjf3xYhN8pXFTpifNuGU"
ADMIN_GROUP_ID = -1003799360830
TEACHER_PASSWORD = "12345"
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB limit

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
    filling_schedule = State()
    waiting_for_topic = State()
    waiting_for_homework = State()
    waiting_for_plan_file = State()
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

def get_next_week_dates():
    today = datetime.now()
    days_until_monday = (7 - today.weekday()) % 7
    if days_until_monday == 0: days_until_monday = 7

    start_of_next_week = today + timedelta(days=days_until_monday)
    return [(start_of_next_week + timedelta(days=i)).strftime("%d.%m.%Y") for i in range(5)]

def get_last_week_range():
    """Avtomatik ravishda o'tgan haftaning Dushanba va Yakshanba kunlarini topadi"""
    today = datetime.now()
    # Dushanba = 0, Yakshanba = 6
    days_to_last_monday = today.weekday() + 7
    last_monday = today - timedelta(days=days_to_last_monday)
    last_sunday = last_monday + timedelta(days=6)

    return f"{last_monday.strftime('%d.%m.%Y')} - {last_sunday.strftime('%d.%m.%Y')}"

def get_schedule_kb(data):
    builder = InlineKeyboardBuilder()
    days = ["Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma"]
    dates = get_next_week_dates()
    schedule = data.get("schedule", {})

    all_done = True
    for i, day in enumerate(days):
        date_str = dates[i]
        status = "✅" if date_str in schedule and "topic" in schedule[date_str] and "hw" in schedule[date_str] else "❌"
        if status == "❌": all_done = False
        builder.button(text=f"{status} {day} ({date_str})", callback_data=f"wd:{date_str}")

    builder.adjust(1)
    if all_done:
        builder.row(InlineKeyboardButton(text="➡️ Davom etish", callback_data="schedule_done"))
    return builder.as_markup()

# ================= HANDLERLAR =================

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.set_state(TeacherReport.waiting_for_contact)
    await message.answer("Assalomu alaykum! Boshlash uchun pastdagi tugma orqali telefon raqamingizni yuboring.", reply_markup=get_contact_kb())

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

@router.message(TeacherReport.waiting_for_subject)
async def process_subject(message: Message, state: FSMContext):
    await state.update_data(subject=message.text)
    await state.set_state(TeacherReport.filling_schedule)
    data = await state.get_data()
    await message.answer("Keyingi hafta uchun mavzu va uy vazifasini kiritish uchun kunni tanlang:", reply_markup=get_schedule_kb(data))

@router.callback_query(TeacherReport.filling_schedule, F.data.startswith("wd:"))
async def select_day(callback: CallbackQuery, state: FSMContext):
    date_str = callback.data.split(":")[1]
    await state.update_data(current_editing_day=date_str)
    await state.set_state(TeacherReport.waiting_for_topic)
    await callback.message.answer(f"📝 {date_str} uchun MAVZUNI kiriting:")
    await callback.answer()

@router.message(TeacherReport.waiting_for_topic)
async def process_topic(message: Message, state: FSMContext):
    await state.update_data(temp_topic=message.text)
    await state.set_state(TeacherReport.waiting_for_homework)
    await message.answer("Ushbu kun uchun UY VAZIFASINI kiriting:")

@router.message(TeacherReport.waiting_for_homework)
async def process_hw(message: Message, state: FSMContext):
    data = await state.get_data()
    day = data['current_editing_day']
    schedule = data.get("schedule", {})
    schedule[day] = {"topic": data['temp_topic'], "hw": message.text}

    await state.update_data(schedule=schedule)
    await state.set_state(TeacherReport.filling_schedule)
    await message.answer("✅ Kun ma'lumotlari saqlandi.", reply_markup=get_schedule_kb(await state.get_data()))

@router.callback_query(TeacherReport.filling_schedule, F.data == "schedule_done")
async def finish_schedule(callback: CallbackQuery, state: FSMContext):
    await state.set_state(TeacherReport.waiting_for_plan_file)
    await callback.message.answer("📄 Haftalik ish rejangizni yuklang (PDF yoki DOCX):\n*(Maksimal hajm: 20 MB)*", parse_mode="Markdown")
    await callback.answer()

# 6. FAYLLAR VA O'LCHAMLARNI TEKSHIRISH
@router.message(TeacherReport.waiting_for_plan_file, F.document)
async def process_plan(message: Message, state: FSMContext):
    if message.document.file_size > MAX_FILE_SIZE:
        await message.answer("⚠️ Fayl hajmi 20 MB dan oshmasligi kerak. Iltimos, kichikroq fayl yuklang:")
        return
    await state.update_data(plan_file_id=message.document.file_id)
    await state.set_state(TeacherReport.waiting_for_test_sample)
    await message.answer("📄 O'tgan hafta test namunasi faylini yuklang:\n*(Maksimal hajm: 20 MB)*", parse_mode="Markdown")

@router.message(TeacherReport.waiting_for_test_sample, F.document)
async def process_sample(message: Message, state: FSMContext):
    if message.document.file_size > MAX_FILE_SIZE:
        await message.answer("⚠️ Fayl hajmi 20 MB dan oshmasligi kerak. Iltimos, kichikroq fayl yuklang:")
        return
    await state.update_data(test_sample_id=message.document.file_id)
    await state.set_state(TeacherReport.waiting_for_test_results)
    await message.answer("📄 O'tgan hafta test natijalari faylini yuklang:\n*(Maksimal hajm: 20 MB)*", parse_mode="Markdown")

@router.message(TeacherReport.waiting_for_test_results, F.document)
async def process_final(message: Message, state: FSMContext):
    if message.document.file_size > MAX_FILE_SIZE:
        await message.answer("⚠️ Fayl hajmi 20 MB dan oshmasligi kerak. Iltimos, kichikroq fayl yuklang:")
        return

    data = await state.get_data()
    test_results_id = message.document.file_id

    # Matnni tayyorlash
    sched_text = ""
    for date, info in data['schedule'].items():
        sched_text += f"🔹 <b>{date}</b>\n   Mavzu: {info['topic']}\n   Vazifa: {info['hw']}\n"

    report_text = (
        "📊 <b>YANGI HAFTALIK HISOBOT</b>\n\n"
        f"📱 <b>Telefon:</b> {data['phone']}\n"
        f"🗓 <b>Sana (Joriy):</b> {data['date_range']}\n"
        f"👤 <b>O'qituvchi:</b> {data['fullname']}\n"
        f"📚 <b>Fan:</b> {data['subject']}\n\n"
        f"<b>Keyingi hafta rejasi:</b>\n{sched_text}"
    )

    try:
        await bot.send_message(ADMIN_GROUP_ID, report_text, parse_mode="HTML")

        # Sigs va Sanalar
        current_sig = f"({data['fullname']}) ({data['date_range']})"
        last_week_dates = get_last_week_range()
        last_week_sig = f"({data['fullname']}) ({last_week_dates})"

        # 1. Haftalik ish reja (Joriy hafta sanasi bilan)
        await bot.send_document(
            ADMIN_GROUP_ID,
            data['plan_file_id'],
            caption=f"📂 Haftalik ish reja {current_sig}"
        )

        # 2. O'tgan hafta test namunasi (O'tgan hafta sanasi bilan)
        await bot.send_document(
            ADMIN_GROUP_ID,
            data['test_sample_id'],
            caption=f"📄 O'tgan hafta test namunasi {last_week_sig}"
        )

        # 3. O'tgan hafta test natijalari (O'tgan hafta sanasi bilan)
        await bot.send_document(
            ADMIN_GROUP_ID,
            test_results_id,
            caption=f"📈 O'tgan hafta test natijalari {last_week_sig}"
        )

        await message.answer("✅ Ma'lumotlaringiz muvaffaqiyatli yuborildi. Rahmat!")
        await message.answer(report_text, parse_mode="HTML")
    except Exception as e:
        logging.error(f"Xatolik: {e}")
        await message.answer("❌ Xatolik yuz berdi. Bot admin guruhga yozolmayapti.")

    await state.clear()

async def main():
    print("Bot ishga tushdi...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())