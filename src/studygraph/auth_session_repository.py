from datetime import UTC, datetime

from sqlalchemy import delete, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from studygraph.document_model import AuthSession


class AuthSessionRepositoryError(Exception):
    """Raised when an authentication session cannot be persisted or read."""


class AuthSessionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(
        self,
        *,
        token_id: str,
        owner_id: str,
        expires_at: datetime,
    ) -> AuthSession:
        auth_session = AuthSession(
            token_id=token_id,
            owner_id=owner_id,
            expires_at=expires_at,
        )
        try:
            self._session.add(auth_session)
            self._session.commit()
            self._session.refresh(auth_session)
        except SQLAlchemyError as error:
            self._session.rollback()
            raise AuthSessionRepositoryError(
                "Could not create authentication session."
            ) from error
        return auth_session

    def is_active(self, *, token_id: str, owner_id: str) -> bool:
        statement = select(AuthSession).where(
            AuthSession.token_id == token_id,
            AuthSession.owner_id == owner_id,
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > datetime.now(UTC),
        )
        try:
            return self._session.scalar(statement) is not None
        except SQLAlchemyError as error:
            raise AuthSessionRepositoryError(
                "Could not validate authentication session."
            ) from error

    def revoke(self, *, token_id: str, owner_id: str) -> bool:
        statement = select(AuthSession).where(
            AuthSession.token_id == token_id,
            AuthSession.owner_id == owner_id,
            AuthSession.revoked_at.is_(None),
        )
        try:
            auth_session = self._session.scalar(statement)
            if auth_session is None:
                return False
            auth_session.revoked_at = datetime.now(UTC)
            self._session.commit()
            return True
        except SQLAlchemyError as error:
            self._session.rollback()
            raise AuthSessionRepositoryError(
                "Could not revoke authentication session."
            ) from error

    def purge_inactive(self) -> int:
        statement = delete(AuthSession).where(
            or_(
                AuthSession.revoked_at.is_not(None),
                AuthSession.expires_at <= datetime.now(UTC),
            )
        )
        try:
            result = self._session.execute(statement)
            self._session.commit()
        except SQLAlchemyError as error:
            self._session.rollback()
            raise AuthSessionRepositoryError(
                "Could not purge inactive authentication sessions."
            ) from error
        return result.rowcount or 0
