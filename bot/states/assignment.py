from aiogram.fsm.state import State, StatesGroup


class AssignmentCreateStates(StatesGroup):
    waiting_for_title = State()
    waiting_for_description = State()
    waiting_for_criteria = State()
    waiting_for_deadline = State()
