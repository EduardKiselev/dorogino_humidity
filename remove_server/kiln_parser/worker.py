# worker.py
import os, re, datetime, json
from sqlalchemy import create_engine, Column, Integer, Float, DateTime, String, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from parser import parse_by_cells

Base = declarative_base()

class ScreenRecord(Base):
    __tablename__ = 'screen_records'
    id = Column(Integer, primary_key=True)
    filename = Column(String, unique=True, nullable=False)
    screen_date = Column(DateTime, nullable=False)  # Из имени файла
    parsed_at = Column(DateTime, default=datetime.datetime.utcnow)
    data_json = Column(Text)  # JSON с результатами парсинга

# Подключение к БД
DB_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@db:5432/sensor_data")
engine = create_engine(DB_URL)
Session = sessionmaker(bind=engine)

def get_date_from_filename(filename):
    match = re.search(r"(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})", filename)
    if match:
        return datetime.datetime.strptime(match.group(1), "%Y-%m-%d_%H-%M-%S")
    return datetime.datetime.now()

def run():
    Base.metadata.create_all(engine)  # Создаст таблицу, если нет
    session = Session()
    
    processed = {r[0] for r in session.query(ScreenRecord.filename).all()}
    screen_dir = "/root/screen"
    
    for filename in os.listdir(screen_dir):
        if not filename.endswith('.png') or filename in processed:
            continue
            
        filepath = os.path.join(screen_dir, filename)
        try:
            data = parse_by_cells(filepath)  # Возвращает list[dict]
            record = ScreenRecord(
                filename=filename,
                screen_date=get_date_from_filename(filename),
                data_json=json.dumps(data, ensure_ascii=False)
            )
            session.add(record)
            session.commit()
            print(f"✓ Processed: {filename}")
        except Exception as e:
            session.rollback()
            print(f"✗ Error {filename}: {e}")
        finally:
            session.close()

if __name__ == "__main__":
    run()