import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Flask configuration
    DEBUG = os.getenv("DEBUG", True)
