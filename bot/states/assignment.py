from aiogram.fsm.state import State, StatesGroup


class AssignmentCreateStates(StatesGroup):
    waiting_for_title = State()
    waiting_for_description = State()
    waiting_for_criteria = State()
    waiting_for_materials = State()
    waiting_for_material_file = State()
    waiting_for_review_model = State()
    waiting_for_review_temperature = State()
    waiting_for_review_system_prompt = State()
    waiting_for_privacy = State()
    waiting_for_deadline = State()


class AssignmentEditStates(StatesGroup):
    waiting_for_review_model = State()
    waiting_for_review_temperature = State()
    waiting_for_review_system_prompt = State()
    waiting_for_deadline = State()
