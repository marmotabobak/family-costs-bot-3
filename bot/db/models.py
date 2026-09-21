from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)

from bot.db.base import Base


class Currency(Base):
    """Currency catalogue.

    ``is_base`` marks the single base currency used for normalization.
    At most one row can have ``is_base=True`` — enforced by a partial unique
    index created in the Alembic migration
    (``idx_currencies_single_base`` WHERE ``is_base = TRUE``).

    ``default_rate`` is the fallback exchange rate when no dated
    :class:`ExchangeRate` record exists for a given date.  For the base
    currency it must be ``1``.
    """

    __tablename__ = "currencies"

    id = Column(Integer, primary_key=True)
    code = Column(String(3), unique=True, nullable=False)
    is_base = Column(Boolean, nullable=False, default=False)
    default_rate = Column(Numeric(20, 10), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("default_rate > 0", name="currencies_default_rate_positive"),
        CheckConstraint("code ~ '^[A-Z]{3}$'", name="currencies_code_format"),
    )


class ExchangeRate(Base):
    """Dated exchange rate for a non-base currency.

    ``rate`` gives how many base-currency units equal 1 unit of
    ``currency_id`` on ``rate_date``.

    Uniqueness of ``(currency_id, rate_date)`` is enforced by the DB
    constraint ``uq_exchange_rates_currency_date``.
    """

    __tablename__ = "exchange_rates"

    id = Column(Integer, primary_key=True)
    currency_id = Column(
        Integer,
        ForeignKey("currencies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rate = Column(Numeric(20, 10), nullable=False)
    rate_date = Column(Date, nullable=False)

    __table_args__ = (
        CheckConstraint("rate > 0", name="exchange_rates_rate_positive"),
        UniqueConstraint(
            "currency_id", "rate_date", name="uq_exchange_rates_currency_date"
        ),
    )


class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    text = Column(Text, nullable=False)
    # Structured amount parsed from ``text``; NULL for legacy rows not yet migrated.
    amount = Column(Numeric(20, 4), nullable=True)
    # FK to currencies; NULL for rows without an assigned currency.
    currency_id = Column(
        Integer,
        ForeignKey("currencies.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (CheckConstraint("user_id > 0", name="messages_user_id_positive"),)


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, server_default="user")  # "admin" or "user"
    password_hash = Column(String(255), nullable=True)  # bcrypt hash, nullable for migration
    created_at = Column(DateTime(timezone=True), server_default=func.now())
