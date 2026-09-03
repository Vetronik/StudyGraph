from typing import Protocol

from studygraph.auth import hash_password, verify_password


class UserAlreadyExistsError(Exception):
    """Raised when a username is already registered."""


class InvalidCredentialsError(Exception):
    """Raised when login credentials are invalid."""


class UserRecord(Protocol):
    username: str
    password_hash: str


class UserRepositoryProtocol(Protocol):
    def add(self, username: str, password_hash: str) -> UserRecord: ...

    def get_by_username(self, username: str) -> UserRecord | None: ...


class AuthService:
    def __init__(self, repository: UserRepositoryProtocol) -> None:
        self._repository = repository

    def register(self, username: str, password: str) -> UserRecord:
        try:
            return self._repository.add(username, hash_password(password))
        except ValueError as error:
            raise UserAlreadyExistsError from error

    def authenticate(self, username: str, password: str) -> UserRecord:
        user = self._repository.get_by_username(username)
        if user is None or not verify_password(password, user.password_hash):
            raise InvalidCredentialsError
        return user
