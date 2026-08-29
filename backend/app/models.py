from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Double, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.database import Base

class Ship(Base):
    __tablename__ = "ships"
    id:Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    mmsi:Mapped[str]= mapped_column(
        String(9),
        unique=True,
        nullable=False,
    )

    name:Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    ship_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    flag: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    imo: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    callsign: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

class ShipPosition(Base):
    __tablename__ = "ship_positions"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    ship_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("ships.id"),
        nullable=False,
    )

    latitude: Mapped[float] = mapped_column(
        Double,
        nullable=False,
    )

    longitude: Mapped[float] = mapped_column(
        Double,
        nullable=False,
    )

    speed: Mapped[float] = mapped_column(
        Double,
        nullable=False,
    )

    course: Mapped[float] = mapped_column(
        Double,
        nullable=False,
    )

    heading: Mapped[float | None] = mapped_column(
        Double,
        nullable=True,
    )

    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    event_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    latitude: Mapped[float] = mapped_column(
        Double,
        nullable=False,
    )

    longitude: Mapped[float] = mapped_column(
        Double,
        nullable=False,
    )

    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    source_name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    source_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )