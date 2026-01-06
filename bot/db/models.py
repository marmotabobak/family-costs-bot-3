from sqlalchemy import CheckConstraint, Column, DateTime, Integer, Text, func

from bot.db.base import Base


class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    text = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (CheckConstraint("user_id > 0", name="messages_user_id_positive"),)
