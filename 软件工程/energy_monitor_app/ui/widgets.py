import tkinter as tk
from tkinter import ttk


def make_tree(parent, columns, headings, widths=None, height=10):
    box = ttk.Frame(parent)
    box.pack(fill="both", expand=True)
    tree = ttk.Treeview(box, columns=columns, show="headings", height=height)
    widths = widths or {}
    for col, heading in zip(columns, headings):
        tree.heading(col, text=heading)
        tree.column(col, width=widths.get(col, 120), anchor="center")
    ybar = ttk.Scrollbar(box, orient="vertical", command=tree.yview)
    xbar = ttk.Scrollbar(box, orient="horizontal", command=tree.xview)
    tree.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
    tree.grid(row=0, column=0, sticky="nsew")
    ybar.grid(row=0, column=1, sticky="ns")
    xbar.grid(row=1, column=0, sticky="ew")
    box.rowconfigure(0, weight=1)
    box.columnconfigure(0, weight=1)
    return tree

