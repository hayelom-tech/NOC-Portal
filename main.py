from dotenv import load_dotenv

load_dotenv()

from server.application import create_app


app = create_app()
