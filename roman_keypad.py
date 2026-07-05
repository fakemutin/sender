from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

ROMAN = {
    0: "0",
    1: "I",
    2: "II",
    3: "III",
    4: "IV",
    5: "V",
    6: "VI",
    7: "VII",
    8: "VIII",
    9: "IX",
}


def code_to_roman(code: str) -> str:
    return " ".join(ROMAN[int(d)] for d in code if d.isdigit())


def roman_keypad(current: str = "") -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text=f"{ROMAN[1]} · 1", callback_data="auth_digit:1"),
            InlineKeyboardButton(text=f"{ROMAN[2]} · 2", callback_data="auth_digit:2"),
            InlineKeyboardButton(text=f"{ROMAN[3]} · 3", callback_data="auth_digit:3"),
        ],
        [
            InlineKeyboardButton(text=f"{ROMAN[4]} · 4", callback_data="auth_digit:4"),
            InlineKeyboardButton(text=f"{ROMAN[5]} · 5", callback_data="auth_digit:5"),
            InlineKeyboardButton(text=f"{ROMAN[6]} · 6", callback_data="auth_digit:6"),
        ],
        [
            InlineKeyboardButton(text=f"{ROMAN[7]} · 7", callback_data="auth_digit:7"),
            InlineKeyboardButton(text=f"{ROMAN[8]} · 8", callback_data="auth_digit:8"),
            InlineKeyboardButton(text=f"{ROMAN[9]} · 9", callback_data="auth_digit:9"),
        ],
        [
            InlineKeyboardButton(text="⌫", callback_data="auth_digit:del"),
            InlineKeyboardButton(text=f"{ROMAN[0]} · 0", callback_data="auth_digit:0"),
            InlineKeyboardButton(text="✓", callback_data="auth_digit:ok"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def code_display(code: str) -> str:
    if not code:
        return "—"
    masked = "•" * len(code)
    return f"{masked}  ({code_to_roman(code)})"
