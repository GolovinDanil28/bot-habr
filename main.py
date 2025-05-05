import asyncio
import aiohttp
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from dotenv import load_dotenv
import os
import logging
from typing import List, Optional
from dataclasses import dataclass

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфигурация
load_dotenv()

@dataclass
class BotConfig:
    """Конфигурация бота"""
    token: str = os.getenv("TELEGRAM_TOKEN")
    chat_id: str = os.getenv("CHAT_ID")
    base_url: str = "https://habr.com"
    search_url: str = (
        f"{base_url}/ru/search/?q=%D1%82%D0%B5%D1%81%D1%82%D0%B8%D1%80%D0%BE%D0%B2%D0%B0%D0%BD%D0%B8%D0%B5+QA"
        "&target_type=posts&order=date"
    )
    user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    max_articles: int = 5
    message_delay: float = 1.0

    def validate(self) -> None:
        """Проверка наличия обязательных параметров"""
        if not self.token or not self.chat_id:
            raise ValueError("TELEGRAM_TOKEN и CHAT_ID должны быть установлены в .env")


class HabrParser:
    
    def __init__(self, config: BotConfig):
        self.config = config

    async def fetch_articles(self) -> List[BeautifulSoup]:
        """Получение сырых данных статей с Habr"""
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(
                    self.config.search_url,
                    headers={'User-Agent': self.config.user_agent}
                ) as response:
                    response.raise_for_status()
                    page = await response.text()
                    soup = BeautifulSoup(page, "html.parser")
                    articles = soup.find_all('article', class_='tm-articles-list__item')
                    return articles[:self.config.max_articles]
            except aiohttp.ClientError as e:
                logger.error(f"Ошибка HTTP-запроса: {e}")
                return []
            except Exception as e:
                logger.error(f"Ошибка парсинга: {e}")
                return []


class ArticleSender:
    """Отправка статей в Telegram"""

    def __init__(self, config: BotConfig):
        self.config = config

    async def send_articles(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Отправка списка статей в Telegram"""
        parser = HabrParser(self.config)
        articles = await parser.fetch_articles()

        if not articles:
            await context.bot.send_message(
                chat_id=self.config.chat_id,
                text="Новых статей не найдено."
            )
            return

        for article in articles:
            try:
                title = self._extract_title(article)
                url = self._extract_url(article)
                await context.bot.send_message(
                    chat_id=self.config.chat_id,
                    text=f"<b>{title}</b>\n{url}",
                    parse_mode='HTML'
                )
                await asyncio.sleep(self.config.message_delay)
            except Exception as e:
                logger.error(f"Ошибка обработки статьи: {e}")
                continue

    def _extract_title(self, article: BeautifulSoup) -> str:
        """Извлечение заголовка статьи"""
        title_elem = article.find('h2', class_='tm-title')
        return title_elem.text.strip() if title_elem else "Без заголовка"

    def _extract_url(self, article: BeautifulSoup) -> str:
        """Извлечение URL статьи"""
        relative_url = article.find('a', class_='tm-title__link')['href']
        return urljoin(self.config.base_url, relative_url)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /start"""
    await update.message.reply_text("Бот запущен. Новые статьи будут отправляться автоматически!")


async def run_bot_once():
    """Запуск бота для одноразовой отправки статей"""
    config = BotConfig()
    try:
        config.validate()
        application = ApplicationBuilder().token(config.token).build()

        # Добавление обработчика команды /start
        application.add_handler(CommandHandler("start", start))

        # Создание контекста для отправки статей
        sender = ArticleSender(config)
        async with application:
            await application.initialize()
            await sender.send_articles(application)
            await application.shutdown()

    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")
        raise


def main():
    """Основная функция для запуска бота"""
    try:
        asyncio.run(run_bot_once())
    except Exception as e:
        logger.error(f"Ошибка при выполнении: {e}")
        exit(1)


if __name__ == "__main__":
    main()