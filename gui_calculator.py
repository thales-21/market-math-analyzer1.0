import tkinter as tk

# ---------------- Window (Gold Frame) ----------------
root = tk.Tk()
root.title("Thales Calculator")
root.geometry("200x350")
root.configure(bg="#D4AF37")  # GOLD FRAME
root.resizable(False, False)

# ---------------- Display (Green Screen) ----------------
display_var = tk.StringVar()
current_expression = ""

display = tk.Entry(
    root,
    textvariable=display_var,
    font=("Helvetica", 28, "bold"),
    bd=0,
    bg="#0b3d0b",              # DARK GREEN SCREEN
    fg="#90EE90",              # LIGHT GREEN TEXT
    justify="right",
    insertbackground="#90EE90"
)
display.pack(fill="both", padx=15, pady=15, ipady=20)

# ---------------- Functions ----------------
def press(value):
    global current_expression
    current_expression += str(value)
    display_var.set(current_expression)

def clear():
    global current_expression
    current_expression = ""
    display_var.set("")

def backspace():
    global current_expression
    current_expression = current_expression[:-1]
    display_var.set(current_expression)

def calculate():
    global current_expression
    try:
        result = str(eval(current_expression))
        display_var.set(result)
        current_expression = result
    except ZeroDivisionError:
        display_var.set("DIV ERROR")
        current_expression = ""
    except Exception:
        display_var.set("ERROR")
        current_expression = ""

# ---------------- Button Frame ----------------
button_frame = tk.Frame(root, bg="#D4AF37")  # GOLD BORDER CONTINUES
button_frame.pack(expand=True, fill="both", padx=15, pady=(0, 15))

for i in range(5):
    button_frame.rowconfigure(i, weight=1)

for j in range(4):
    button_frame.columnconfigure(j, weight=1)

# ---------------- Button Maker ----------------
def make_button(text, command, row, col):
    button = tk.Button(
        button_frame,
        text=text,
        command=command,
        font=("Helvetica", 20, "bold"),
        bd=0,
        bg="#C0C0C0",          # SILVER BUTTON
        fg="#D4AF37",          # GOLD TEXT
        activebackground="#A9A9A9",
        activeforeground="#FFD700",
        relief="flat"
    )
    button.grid(row=row, column=col, sticky="nsew", padx=8, pady=8)

# ---------------- Buttons ----------------
make_button("C", clear, 0, 0)
make_button("(", lambda: press("("), 0, 1)
make_button(")", lambda: press(")"), 0, 2)
make_button("/", lambda: press("/"), 0, 3)

make_button("7", lambda: press("7"), 1, 0)
make_button("8", lambda: press("8"), 1, 1)
make_button("9", lambda: press("9"), 1, 2)
make_button("*", lambda: press("*"), 1, 3)

make_button("4", lambda: press("4"), 2, 0)
make_button("5", lambda: press("5"), 2, 1)
make_button("6", lambda: press("6"), 2, 2)
make_button("-", lambda: press("-"), 2, 3)

make_button("1", lambda: press("1"), 3, 0)
make_button("2", lambda: press("2"), 3, 1)
make_button("3", lambda: press("3"), 3, 2)
make_button("+", lambda: press("+"), 3, 3)

make_button("0", lambda: press("0"), 4, 0)
make_button(".", lambda: press("."), 4, 1)
make_button("=", calculate, 4, 2)
make_button("⌫", backspace, 4, 3)

# ---------------- Run ----------------
root.mainloop()
