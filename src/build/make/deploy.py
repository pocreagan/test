import shutil
from pathlib import Path


def main():
    src = Path(r'C:\Projects\test\build\bin\Debug')
    dest = Path(r'W:\Test Data Backup\test\bin\bin')

    assert src.exists()
    assert dest.exists()

    shutil.copytree(src, dest / src.name)


if __name__ == '__main__':
    main()
