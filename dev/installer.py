import os
import sys
import subprocess

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REQUIREMENTS_F = os.path.join(BASE_DIR, '../requirements.txt')
FLAG_F = os.path.join(BASE_DIR, '../.installed')


def check_install():
    if os.path.exists(FLAG_F):
        return True

    if not(os.path.exists(REQUIREMENTS_F)):
        print('requirements.txt not found')
        sys.exit(1)

    try:
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-r', REQUIREMENTS_F])
        with open(FLAG_F, 'w',) as f:
            f.write('installed')

    except subprocess.CalledProcessError as E:
        print('install script was executed')
        print(E)
        sys.exit(1)

check_install()