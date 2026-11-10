import uuid

from common.database import get_db
from modules.auth.service import UserService

session = next(get_db())

userService = UserService(session)

def test_get_user_by_id(user_id: uuid.UUID):
    user = userService.get_username_by_id(user_id)
    print(user)

if __name__ == "__main__":
    try:
        test_get_user_by_id(uuid.UUID("eda60678-cf24-45bf-8e43-c70701464b23"))
    except Exception as e:
        print(e)