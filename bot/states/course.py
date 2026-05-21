from aiogram.fsm.state import State, StatesGroup


class CourseCreateStates(StatesGroup):
    waiting_for_name = State()


class JoinCourseStates(StatesGroup):
    waiting_for_code = State()
