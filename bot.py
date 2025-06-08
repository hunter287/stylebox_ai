import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from config import TELEGRAM_BOT_TOKEN
from color_analysis import ColorAnalyzer
from database import init_db, get_db, User, ColorAnalysis
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize color analyzer
color_analyzer = ColorAnalyzer()

# Create uploads directory if it doesn't exist
UPLOADS_DIR = "uploads"
if not os.path.exists(UPLOADS_DIR):
    os.makedirs(UPLOADS_DIR)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /start is issued."""
    await update.message.reply_text(
        'Привет! Я бот для определения цветотипа. '
        'Отправьте мне свою фотографию, и я определю ваш цветотип '
        'и дам рекомендации по подбору цветов.'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /help is issued."""
    await update.message.reply_text(
        'Отправьте мне свою фотографию, и я определю ваш цветотип. '
        'Убедитесь, что фотография сделана при хорошем освещении '
        'и на ней хорошо видно ваше лицо.'
    )

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the photo message and determine color type."""
    # Get the photo file
    photo = update.message.photo[-1]  # Get the largest photo
    file = await context.bot.get_file(photo.file_id)
    
    # Create unique filename
    filename = f"{update.effective_user.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
    file_path = os.path.join(UPLOADS_DIR, filename)
    
    # Download the photo
    await file.download_to_drive(file_path)
    
    # Analyze the photo
    try:
        colors = color_analyzer.analyze_image(file_path)
        color_type = color_analyzer.determine_color_type(colors)
        recommendations = color_analyzer.get_color_recommendations(color_type)
        
        # Save to database
        db = next(get_db())
        user = db.query(User).filter_by(telegram_id=update.effective_user.id).first()
        if not user:
            user = User(
                telegram_id=update.effective_user.id,
                username=update.effective_user.username
            )
            db.add(user)
            db.commit()
        
        analysis = ColorAnalysis(
            user_id=user.id,
            color_type=color_type,
            image_path=file_path
        )
        db.add(analysis)
        db.commit()
        
        # Prepare response message
        message = f'Ваш цветотип: {color_type}\n\n'
        message += f'Описание: {recommendations["description"]}\n\n'
        
        if recommendations["recommended_colors"]:
            message += 'Рекомендуемые цвета:\n'
            message += '\n'.join(f'• {color}' for color in recommendations["recommended_colors"])
            message += '\n\n'
        
        if recommendations["avoid_colors"]:
            message += 'Цвета, которых стоит избегать:\n'
            message += '\n'.join(f'• {color}' for color in recommendations["avoid_colors"])
        
        # Send result
        await update.message.reply_text(message)
        
    except Exception as e:
        logger.error(f"Error processing photo: {e}")
        await update.message.reply_text(
            'Извините, произошла ошибка при обработке фотографии. '
            'Пожалуйста, попробуйте еще раз.'
        )
    finally:
        # Clean up the file
        if os.path.exists(file_path):
            os.remove(file_path)

def main():
    """Start the bot."""
    # Initialize database
    init_db()
    
    # Create the Application
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    # Start the Bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main() 