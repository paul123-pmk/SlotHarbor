"""Errors safe to present to a user without exposing database internals."""


class DomainError(Exception):
    def __init__(self, message: str, status: int = 400, code: str = "invalid"):
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code


def require(condition: bool, message: str, status: int = 400, code: str = "invalid"):
    if not condition:
        raise DomainError(message, status, code)
