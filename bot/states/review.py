from aiogram.fsm.state import State, StatesGroup


class ReviewEditStates(StatesGroup):
    waiting_for_edited_text = State()
    waiting_for_feedback_text = State()
    waiting_for_temperature = State()
    waiting_for_system_prompt = State()
