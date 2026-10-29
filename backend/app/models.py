from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base

ROLES = ("admin", "doctor", "nurse")
STAFF_ROLES = ("doctor", "nurse")
PERIODS = ("Morning", "Evening", "Night")
PERIOD_ORDER = {p: i for i, p in enumerate(PERIODS)}


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(10))
    department: Mapped[str] = mapped_column(String(100), default="")
    phone: Mapped[str] = mapped_column(String(30), default="")
    active: Mapped[bool] = mapped_column(default=True)


class Shift(Base):
    __tablename__ = "shifts"
    __table_args__ = (UniqueConstraint("date", "period", "ward"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    period: Mapped[str] = mapped_column(String(10))
    ward: Mapped[str] = mapped_column(String(60), default="General")
    doctors_needed: Mapped[int] = mapped_column(default=1)
    nurses_needed: Mapped[int] = mapped_column(default=0)

    @property
    def label(self) -> str:
        return f"{self.date:%a %d %b} · {self.period} · {self.ward}"

    @property
    def sort_key(self):
        return (self.date, PERIOD_ORDER.get(self.period, 9), self.ward)


class Availability(Base):
    __tablename__ = "availability"
    __table_args__ = (UniqueConstraint("user_id", "shift_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    shift_id: Mapped[int] = mapped_column(ForeignKey("shifts.id", ondelete="CASCADE"))


class Assignment(Base):
    __tablename__ = "assignments"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    shift_id: Mapped[int] = mapped_column(ForeignKey("shifts.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(10))
    slot_label: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="assigned")  # assigned | accepted | issue_raised
    published: Mapped[bool] = mapped_column(default=False)

    user: Mapped[User] = relationship()
    shift: Mapped[Shift] = relationship()


class Request(Base):
    __tablename__ = "requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    assignment_id: Mapped[int | None] = mapped_column(ForeignKey("assignments.id", ondelete="SET NULL"))
    shift_id: Mapped[int | None] = mapped_column(ForeignKey("shifts.id", ondelete="SET NULL"))
    type: Mapped[str] = mapped_column(String(10))  # swap | leave | issue
    message: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(10), default="open")  # open | approved | rejected
    admin_note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    user: Mapped[User] = relationship()
    shift: Mapped[Shift | None] = relationship()
