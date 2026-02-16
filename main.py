import asyncio
import logging
import re
from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import Message, ContentType
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# ================= CONFIGURATION =================
# Replace these with your actual values
BOT_TOKEN = "8514239580:AAGD9c3Sls4WGwLmjf3xYhN8pXFTpifNuGU"
ADMIN_GROUP_ID = -1003799360830  # Replace with your Group Chat ID
TEACHER_PASSWORD = "12345"       # The password teachers must enter

# Configure logging
logging.basicConfig(level=logging.INFO)

# Initialize Bot and Dispatcher
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()
dp.include_router(router)

# ================= STATE MACHINE (FSM) =================
class TeacherReport(StatesGroup):
    waiting_for_password = State()
    waiting_for_date_range = State()
    waiting_for_fullname = State()
    waiting_for_subject = State()
    waiting_for_hours = State()
    waiting_for_plan_file = State()
    waiting_for_test_sample = State()
    waiting_for_test_results = State()

# ================= HANDLERS =================

# 1. START & PASSWORD REQUEST
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    """
    Triggered when user types /start.
    Asks for password to verify identity.
    """
    await state.set_state(TeacherReport.waiting_for_password)
    await message.answer("Assalomu alaykum!\n\nIltimos, maktab o‘qituvchisi ekanligingizni tasdiqlash uchun parolni kiriting:")

# 2. PASSWORD VALIDATION
@router.message(TeacherReport.waiting_for_password)
async def process_password(message: Message, state: FSMContext):
    if message.text == TEACHER_PASSWORD:
        await state.set_state(TeacherReport.waiting_for_date_range)
        await message.answer("✅ Parol to‘g‘ri.\n\nQaysi sana oralig‘i uchun ma’lumot topshiryapsiz?\n(Masalan: 09.02.2026 - 15.02.2026)")
    else:
        await message.answer("❌ Parol noto‘g‘ri. Iltimos, qaytadan urinib ko‘ring:")

# 3. DATE RANGE
@router.message(TeacherReport.waiting_for_date_range)
async def process_date(message: Message, state: FSMContext):
    # Simple regex to validate basic date format (DD.MM.YYYY - DD.MM.YYYY)
    # This is a basic check, you can make it stricter if needed.
    if re.search(r'\d{2}\.\d{2}\.\d{4}.*?-.*?\d{2}\.\d{2}\.\d{4}', message.text):
        await state.update_data(date_range=message.text)
        await state.set_state(TeacherReport.waiting_for_fullname)
        await message.answer("Ism va familiyangizni kiriting:")
    else:
        await message.answer("⚠️ Iltimos, sanani to‘g‘ri formatda kiriting.\nNamuna: 09.02.2026 - 15.02.2026")

# 4. FULL NAME
@router.message(TeacherReport.waiting_for_fullname)
async def process_fullname(message: Message, state: FSMContext):
    await state.update_data(fullname=message.text)
    await state.set_state(TeacherReport.waiting_for_subject)
    await message.answer("Qaysi fan bo‘yicha dars berasiz?")

# 5. SUBJECT
@router.message(TeacherReport.waiting_for_subject)
async def process_subject(message: Message, state: FSMContext):
    await state.update_data(subject=message.text)
    await state.set_state(TeacherReport.waiting_for_hours)
    await message.answer("Ushbu haftada jami nechta dars soati o‘tdingiz? (Faqat raqam yozing)")

# 6. WEEKLY HOURS
@router.message(TeacherReport.waiting_for_hours)
async def process_hours(message: Message, state: FSMContext):
    if message.text.isdigit():
        await state.update_data(hours=message.text)
        await state.set_state(TeacherReport.waiting_for_plan_file)
        await message.answer("📄 Haftalik ish rejangizni yuklang (PDF yoki DOCX):")
    else:
        await message.answer("⚠️ Iltimos, faqat raqam kiriting (masalan: 18).")

# 7. PLAN FILE UPLOAD
@router.message(TeacherReport.waiting_for_plan_file, F.document)
async def process_plan_file(message: Message, state: FSMContext):
    # Store the file_id (Telegram server reference)
    await state.update_data(plan_file_id=message.document.file_id)
    await state.set_state(TeacherReport.waiting_for_test_sample)
    await message.answer("📄 O‘tgan hafta olingan test namunasi faylini yuklang:")

# Handle invalid content type for Plan File
@router.message(TeacherReport.waiting_for_plan_file)
async def warning_plan_file(message: Message):
    await message.answer("⚠️ Iltimos, fayl (hujjat) yuklang.")

# 8. TEST SAMPLE UPLOAD
@router.message(TeacherReport.waiting_for_test_sample, F.document)
async def process_test_sample(message: Message, state: FSMContext):
    await state.update_data(test_sample_id=message.document.file_id)
    await state.set_state(TeacherReport.waiting_for_test_results)
    await message.answer("📄 Test natijalari faylini yuklang:")

# Handle invalid content type for Test Sample
# 9. TEST RESULTS & FINAL SUBMISSION
@router.message(TeacherReport.waiting_for_test_results, F.document)
async def process_final_step(message: Message, state: FSMContext):
    # 1. Save final file ID
    data = await state.get_data()
    test_results_id = message.document.file_id

    # 2. Construct the Report Text (Summary)
    report_text = (
        "📊 <b>YANGI HAFTALIK HISOBOT</b>\n\n"
        f"🗓 <b>Sana:</b> {data['date_range']}\n"
        f"👤 <b>O‘qituvchi:</b> {data['fullname']}\n"
        f"📚 <b>Fan:</b> {data['subject']}\n"
        f"⏳ <b>Dars soatlari:</b> {data['hours']}\n\n"
        "<i>Quyida yuklangan hujjatlar:</i>"
    )

    try:
        # 3. Send Text Summary to Admin Group
        await bot.send_message(chat_id=ADMIN_GROUP_ID, text=report_text, parse_mode="HTML")

        # 4. Prepare the signature for captions
        # Format: (Valisher Botirov) (10.02.2026 - 15.02.2026)
        file_signature = f"({data['fullname']}) ({data['date_range']})"

        # 5. Send the 3 Files to Admin Group with specific captions
        await bot.send_document(
            chat_id=ADMIN_GROUP_ID,
            document=data['plan_file_id'],
            caption=f"📂 Haftalik ish reja {file_signature}"
        )

        await bot.send_document(
            chat_id=ADMIN_GROUP_ID,
            document=data['test_sample_id'],
            caption=f"📄 Test namunasi {file_signature}"
        )

        await bot.send_document(
            chat_id=ADMIN_GROUP_ID,
            document=test_results_id,
            caption=f"📈 Test natijalari {file_signature}"
        )

        # 6. Confirm success to user
        await message.answer("✅ Ma’lumotlaringiz muvaffaqiyatli yuborildi. Rahmat!")

    except Exception as e:
        logging.error(f"Error sending report: {e}")
        await message.answer("❌ Xatolik yuz berdi. Bot admin guruhga yozolmayapti. ID yoki ruxsatlarni tekshiring.")

    # 7. Finish state
    await state.clear()
# Handle invalid content type for Test Results
@router.message(TeacherReport.waiting_for_test_results)
async def warning_test_results(message: Message):
    await message.answer("⚠️ Iltimos, fayl (hujjat) yuklang.")

# ================= MAIN EXECUTION =================
async def main():
    print("Bot ishga tushdi...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot to‘xtatildi.")