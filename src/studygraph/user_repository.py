from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from studygraph.document_model import User
from studygraph.document_repository import DocumentRepositoryError


class UserRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, username: str, password_hash: str) -> User:
        user = User(username=username, password_hash=password_hash)
        try:
            self._session.add(user)
            self._session.commit()
            self._session.refresh(user)
            return user
        except IntegrityError as error:
            self._session.rollback()
            raise ValueError("Username already exists.") from error
        except SQLAlchemyError as error:
            self._session.rollback()
            raise DocumentRepositoryError("Could not save user.") from error

    def get_by_username(self, username: str) -> User | None:
        try:
            return self._session.scalar(
                select(User).where(User.username == username),
            )
        except SQLAlchemyError as error:
            raise DocumentRepositoryError("Could not load user.") from error
