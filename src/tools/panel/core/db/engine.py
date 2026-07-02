from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.engine import Engine

from tools.config import load_settings

settings = load_settings()
engine = create_engine(settings.database.url)
SessionLocal = sessionmaker(bind=engine)


