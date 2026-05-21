from aiogram.fsm.state import State, StatesGroup


class SubmissionStates(StatesGroup):
    waiting_for_content = State()
