from rubpy.bot.models import (
    Keypad,
    KeypadRow,
    Button,
    ButtonTypeEnum
)
def get_keyboard():
    return Keypad(
        rows=[
            KeypadRow(
                buttons=[
                    Button(
                        id="pv_get_help",
                        type=ButtonTypeEnum.SIMPLE,
                        button_text="🚀 راهنما"
                    ),
                ]
            ),
            KeypadRow(
                buttons=[
                    Button(
                        id="my_groups",
                        type=ButtonTypeEnum.SIMPLE,
                        button_text="📋 گروه‌های من",
                    )
                ]
            )
        ],
        resize_keyboard=True,
        on_time_keyboard=False,
    )