"""Base class dùng chung cho toàn bộ SQLAlchemy ORM model."""
from sqlalchemy.orm import DeclarativeBase

from derma_shared.constants import DB_NAMING_CONVENTION


class Base(DeclarativeBase):
    """Base class cho toàn bộ model. Import model cụ thể trong `app/models/__init__.py`."""

    pass


Base.metadata.naming_convention = DB_NAMING_CONVENTION
