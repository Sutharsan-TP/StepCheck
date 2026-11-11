"""Request-level limits shared by API schemas."""

from app.core.equation_parser import MAX_INPUT_LENGTH

MIN_STEPS = 2
MAX_STEPS = 30
MAX_STEP_LENGTH = MAX_INPUT_LENGTH
MAX_REQUEST_ID_LENGTH = 100
