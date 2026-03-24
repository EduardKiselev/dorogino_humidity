# worker.py
import os
import re
import time
import json
import logging
import datetime
from sqlalchemy import create_engine, Column, Integer, DateTime, String, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from parser import parse_by_cells

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

Base = declarative_base()

class ScreenRecord(Base):
    __tablename__ = 'screen_records'
    id = Column(Integer, primary_key=True)
    filename = Column(String, unique=True, nullable=False, index=True)
    screen_date = Column(DateTime, nullable=False)
    parsed_at = Column(DateTime, default=datetime.datetime.utcnow)
    data_json = Column(Text)

DB_URL = os.getenv("DATABASE_URL", "postgresql://postgres_userok:postgres_passwordok@db:5432/sensor_data")
SCREEN_DIR = os.getenv("SCREEN_DIR", "/root/screen")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "60"))  # секунды

def get_date_from_filename(filename):
    match = re.search(r"(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})", filename)
    if match:
        return datetime.datetime.strptime(match.group(1), "%Y-%m-%d_%H-%M-%S")
    return datetime.datetime.now()

def process_new_files():
    """Обрабатывает новые скриншоты за один цикл."""
    engine = create_engine(DB_URL)
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        # Создаём таблицу, если нет (идемпотентно)
        Base.metadata.create_all(engine)
        
        # Получаем множество уже обработанных имён
        processed = {r[0] for r in session.query(ScreenRecord.filename).all()}
        logger.info(f"Already Processed - {processed}")
        if not os.path.isdir(SCREEN_DIR):
            logger.warning(f"Directory not found: {SCREEN_DIR}")
            return
            
        new_files = [
            f for f in os.listdir(SCREEN_DIR)
            if f.endswith('.png') and f not in processed
        ]
        
        
        if not new_files:
            logger.debug("No new files to process")
            return

    
        logger.info(f"Found {len(new_files)} new file(s) - {new_files}")
        
        for filename in new_files:
            filepath = os.path.join(SCREEN_DIR, filename)
            logger.info(f"Parsing {filepath}")
            try:
                data = parse_by_cells(filepath)
                logger.info({data})
                record = ScreenRecord(
                    filename=filename,
                    screen_date=get_date_from_filename(filename),
                    data_json=json.dumps(data, ensure_ascii=False)
                )
                session.add(record)
                session.commit()
                logger.info(f"✓ Processed: {filename} ({len(data)} rows)")
            except Exception as e:
                session.rollback()
                logger.error(f"✗ Error processing {filename}: {e}", exc_info=True)
                
    except Exception as e:
        logger.error(f"Database error: {e}", exc_info=True)
    finally:
        session.close()
        engine.dispose()  # Освобождаем соединения

def main():
    logger.info(f"Worker started. Polling {SCREEN_DIR} every {POLL_INTERVAL}s")
    
    while True:
        try:
            logger.info("Start Process")
            process_new_files()
        except Exception as e:
            logger.error(f"Unhandled error in main loop: {e}", exc_info=True)
        
        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()