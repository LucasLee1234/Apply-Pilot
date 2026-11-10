class AppError(Exception):

    code = "AppError"

    def __init__(self, msg: str):
        super().__init__(msg)