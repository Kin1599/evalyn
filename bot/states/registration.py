from aiogram.fsm.state import State, StatesGroup


class RegistrationStates(StatesGroup):
    waiting_for_name = State()


class ProfileStates(StatesGroup):
    waiting_for_new_name = State()
