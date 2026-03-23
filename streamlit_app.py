from pathlib import Path
import runpy

APP = Path(__file__).resolve().parent / 'apps' / 'streamlit' / 'app.py'
runpy.run_path(str(APP), run_name='__main__')
