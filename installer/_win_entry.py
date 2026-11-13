import os, sys
base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
core = os.path.join(base, 'omnibrowser-core.exe')
if os.path.isfile(core):
    os.environ['OMNIBROWSER_CORE'] = core
from src.main import main
if __name__ == '__main__':
    main()
