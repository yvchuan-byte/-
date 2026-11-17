import argparse
from pathlib import Path
import tkinter as tk

from desktop_app import DesktopApp


ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description="智慧园区监测系统 v2.0")
    parser.add_argument("--db", default=str(ROOT / "energy_monitor.db"))
    args = parser.parse_args()
    root = tk.Tk()
    DesktopApp(root, args.db)
    root.mainloop()


if __name__ == "__main__":
    main()
