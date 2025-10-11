# app/api/v1/services/router.py

from fastapi import APIRouter
# 1. Import from your new consolidated 'gemini.py' file.
from . import gemini

services_router = APIRouter()

# 2. Include the router from the 'gemini' module.
# 3. We add a prefix to group all gemini-related routes under a common path.
# 4. We add a tag to group them cleanly in the API documentation.
services_router.include_router(
    gemini.router,
    prefix="/gemini",
)

# This is now ready for you to add other services in the future.
# For example, if you add an 'anthropic.py' endpoint file:
#
# from . import anthropic
# services_router.include_router(
#     anthropic.router,
#     prefix="/anthropic",
#     tags=["Anthropic AI Services"]
# )