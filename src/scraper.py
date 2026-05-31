

import os
import sys
import json
import logging
import asyncio
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any
from dotenv import load_dotenv

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError, FloodWaitError
from telethon.tl.types import MessageMediaPhoto


# Load environment variables
load_dotenv()

# Configuration
API_ID = os.getenv('TELEGRAM_API_ID')
API_HASH = os.getenv('TELEGRAM_API_HASH')
PHONE = os.getenv('TELEGRAM_PHONE')
SESSION_NAME = 'telegram_scraper'

# Channels from which to download images (others will still be scraped, but images won't be downloaded)
# Channel names should match exactly as they appear in Telegram (can be with or without @)
# You can customize this list to add/remove channels
IMAGE_DOWNLOAD_CHANNELS = [
    'CheMed123',        # CheMed Telegram Channel (https://t.me/CheMed123)
    # 'lobelia4cosmetics' # Lobelia Cosmetics - DISABLED (images won't be downloaded)
]

# Directory paths
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / 'data' / 'raw'
IMAGES_DIR = DATA_DIR / 'images'
MESSAGES_DIR = DATA_DIR / 'telegram_messages'
LOGS_DIR = BASE_DIR / 'logs'

# Create directories if they don't exist
IMAGES_DIR.mkdir(parents=True, exist_ok=True)
MESSAGES_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOGS_DIR / f'scraper_{datetime.now().strftime("%Y%m%d")}.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class TelegramScraper:
    """Scraper class for extracting data from Telegram channels."""
    
    def __init__(self, api_id: str, api_hash: str, phone: str, session_name: str = 'telegram_scraper'):
        """
        Initialize the Telegram scraper.
        
        Args:
            api_id: Telegram API ID
            api_hash: Telegram API Hash
            phone: Phone number for authentication
            session_name: Name for the session file
        """
        self.api_id = api_id
        self.api_hash = api_hash
        self.phone = phone
        self.session_name = session_name
        self.client = None
        
    async def connect(self):
        """Initialize and connect to Telegram client."""
        try:
            self.client = TelegramClient(self.session_name, self.api_id, self.api_hash)
            await self.client.connect()
            
            if not await self.client.is_user_authorized():
                await self.client.send_code_request(self.phone)
                logger.info(f"Verification code sent to {self.phone}")
                code = input('Enter the code: ')
                
                try:
                    await self.client.sign_in(self.phone, code)
                except SessionPasswordNeededError:
                    password = input('Two-step verification enabled. Enter your password: ')
                    await self.client.sign_in(password=password)
            
            logger.info("Successfully connected to Telegram")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Telegram: {e}")
            return False
    
    async def download_image(self, message, channel_name: str, message_id: int, download_enabled: bool = True) -> Optional[str]:
        """
        Download image from a message if present.
        
        Args:
            message: Telethon message object
            channel_name: Name of the channel
            message_id: ID of the message
            download_enabled: Whether to actually download the image (False to skip)
            
        Returns:
            Path to downloaded image or None
        """
        # Skip download if disabled for this channel
        if not download_enabled:
            return None
        
        if not hasattr(message, 'media') or message.media is None:
            return None
        
        if isinstance(message.media, MessageMediaPhoto):
            try:
                # Create channel-specific directory
                channel_image_dir = IMAGES_DIR / channel_name
                channel_image_dir.mkdir(parents=True, exist_ok=True)
                
                # Download image
                image_path = channel_image_dir / f"{message_id}.jpg"
                await self.client.download_media(message.media, str(image_path))
                
                logger.info(f"Downloaded image: {image_path}")
                return str(image_path.relative_to(BASE_DIR))
            except Exception as e:
                logger.error(f"Failed to download image for message {message_id}: {e}")
                return None
        
        return None
    
    def extract_message_data(self, message, channel_name: str) -> Dict[str, Any]:
        """
        Extract relevant data from a Telegram message.
        
        Args:
            message: Telethon message object
            channel_name: Name of the channel
            
        Returns:
            Dictionary containing message data
        """
        has_media = hasattr(message, 'media') and message.media is not None
        image_path = None
        
        # Download image if present (synchronous extraction, async download happens separately)
        # Note: Image download will be handled in the async scraping method
        
        return {
            'message_id': message.id,
            'channel_name': channel_name,
            'message_date': message.date.isoformat() if message.date else None,
            'message_text': message.text or '',
            'has_media': has_media,
            'image_path': image_path,  # Will be set during async processing
            'views': message.views if hasattr(message, 'views') else None,
            'forwards': message.forwards if hasattr(message, 'forwards') else None,
        }
    
    async def scrape_channel(self, channel_name: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Scrape messages from a Telegram channel.
        
        Args:
            channel_name: Name of the Telegram channel (with or without @)
            limit: Maximum number of messages to scrape (None for all)
            
        Returns:
            List of message data dictionaries
        """
        if not self.client or not self.client.is_connected():
            logger.error("Client not connected. Call connect() first.")
            return []
        
        # Normalize channel name (remove @ if present)
        channel_name = channel_name.lstrip('@')
        
        messages_data = []
        
        try:
            logger.info(f"Starting to scrape channel: {channel_name}")
            
            # Get entity (channel)
            entity = await self.client.get_entity(channel_name)
            logger.info(f"Found channel: {entity.title}")
            
            # Check if images should be downloaded for this channel
            should_download_images = channel_name.lower() in [ch.lower() for ch in IMAGE_DOWNLOAD_CHANNELS]
            if not should_download_images:
                logger.info(f"Image download disabled for channel: {channel_name}")
            
            # Scrape messages
            async for message in self.client.iter_messages(entity, limit=limit):
                try:
                    # Extract message data
                    message_data = self.extract_message_data(message, channel_name)
                    
                    # Download image if present and enabled for this channel
                    image_path = await self.download_image(message, channel_name, message.id, should_download_images)
                    if image_path:
                        message_data['image_path'] = image_path
                    
                    messages_data.append(message_data)
                    
                except FloodWaitError as e:
                    logger.warning(f"Rate limit hit. Waiting {e.seconds} seconds...")
                    await asyncio.sleep(e.seconds)
                    continue
                except Exception as e:
                    logger.error(f"Error processing message {message.id}: {e}")
                    continue
            
            logger.info(f"Scraped {len(messages_data)} messages from {channel_name}")
            
        except Exception as e:
            logger.error(f"Error scraping channel {channel_name}: {e}")
        
        return messages_data
    
    def save_messages_to_datalake(self, messages: List[Dict[str, Any]], channel_name: str, date: Optional[datetime] = None):
        """
        Save messages to data lake structure.
        
        Args:
            messages: List of message data dictionaries
            channel_name: Name of the channel
            date: Date for partitioning (defaults to today)
        """
        if not messages:
            logger.warning(f"No messages to save for channel {channel_name}")
            return
        
        # Use provided date or current date
        if date is None:
            date = datetime.now()
        
        # Create partitioned directory: YYYY-MM-DD/channel_name.json
        date_str = date.strftime('%Y-%m-%d')
        date_dir = MESSAGES_DIR / date_str
        date_dir.mkdir(parents=True, exist_ok=True)
        
        # Save as JSON file
        output_file = date_dir / f"{channel_name}.json"
        
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(messages, f, ensure_ascii=False, indent=2)
            
            logger.info(f"Saved {len(messages)} messages to {output_file}")
        except Exception as e:
            logger.error(f"Failed to save messages to {output_file}: {e}")


async def main():
    """Main function to run the scraper."""
    # Validate environment variables
    if not all([API_ID, API_HASH, PHONE]):
        logger.error("Missing required environment variables. Please check your .env file.")
        logger.error("Required: TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE")
        return False
    
    # Get channels from environment or use defaults
    channels_env = os.getenv('TELEGRAM_CHANNELS', 'CheMed123,lobelia4cosmetics,tikvahpharma')
    channels = [ch.strip() for ch in channels_env.split(',')]
    
    # Initialize scraper
    scraper = TelegramScraper(API_ID, API_HASH, PHONE)
    
    # Connect to Telegram
    if not await scraper.connect():
        logger.error("Failed to connect to Telegram. Exiting.")
        return False
    
    # Scrape each channel
    total_messages = 0
    total_images_downloaded = 0
    
    for channel in channels:
        try:
            logger.info(f"Processing channel: {channel}")
            messages = await scraper.scrape_channel(channel, limit=None)  # Set limit=None to get all messages
            
            if messages:
                scraper.save_messages_to_datalake(messages, channel)
                
                # Count images downloaded for this channel
                images_count = sum(1 for msg in messages if msg.get('image_path'))
                total_images_downloaded += images_count
                total_messages += len(messages)
                
                logger.info(f"Successfully processed {len(messages)} messages from {channel} ({images_count} images downloaded)")
            else:
                logger.warning(f"No messages found for channel {channel}")
                
        except Exception as e:
            logger.error(f"Error processing channel {channel}: {e}")
            continue
    
    # Disconnect
    await scraper.client.disconnect()
    
    # Final summary
    logger.info("=" * 60)
    logger.info("SCRAPING SUMMARY")
    logger.info("=" * 60)
    logger.info(f"Total messages scraped: {total_messages}")
    logger.info(f"Total images downloaded: {total_images_downloaded}")
    logger.info(f"Image download channels: {', '.join(IMAGE_DOWNLOAD_CHANNELS)}")
    logger.info("Scraping completed. Client disconnected.")
    return True


if __name__ == '__main__':
    import asyncio
    sys.exit(0 if asyncio.run(main()) else 1)
