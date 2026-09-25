from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, Date, DateTime, Double, ForeignKey, Integer, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import JSONB
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
        String(10),
        unique=True,
        nullable=False,
    )

    name:Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    ship_type: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )
    ship_type_cn_raw: Mapped[str | None] = mapped_column(String(100), nullable=True)
    dwt_t: Mapped[float | None] = mapped_column(Double, nullable=True)

    flag: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    imo: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    callsign: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    length_m: Mapped[float | None] = mapped_column(Double, nullable=True)
    width_m: Mapped[float | None] = mapped_column(Double, nullable=True)

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

    # Supplier Unix seconds; import must derive recorded_at from this value.
    unix_time: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    nav_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Preserve supplier ROT; units/encoding must be confirmed before analysis.
    rot: Mapped[float | None] = mapped_column(Double, nullable=True)
    draught_m: Mapped[float | None] = mapped_column(Double, nullable=True)
    destination: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ais_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    eta_text: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_batch_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    source_row: Mapped[int | None] = mapped_column(Integer, nullable=True)
    data_source: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="unknown",
    )

class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    event_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    title_zh: Mapped[str] = mapped_column(Text, nullable=False)
    summary_zh: Mapped[str] = mapped_column(Text, nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    event_datetime: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    event_time_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_location_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_region: Mapped[str | None] = mapped_column(String(32), nullable=True)
    event_lat: Mapped[float | None] = mapped_column(Double, nullable=True)
    event_lng: Mapped[float | None] = mapped_column(Double, nullable=True)
    mentioned_vessels: Mapped[list] = mapped_column(JSONB, nullable=False)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_path: Mapped[str | None] = mapped_column(String, nullable=True)
    event_points: Mapped[list | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
    geo_method: Mapped[str | None] = mapped_column(String(32), nullable=True)
    geo_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    coverage_count: Mapped[int] = mapped_column(Integer, nullable=False)
    perspectives: Mapped[list] = mapped_column(JSONB, nullable=False)
    story_ids: Mapped[list] = mapped_column(JSONB, nullable=False)
    publish_date_min: Mapped[date | None] = mapped_column(Date, nullable=True)
    publish_date_max: Mapped[date | None] = mapped_column(Date, nullable=True)

class News(Base):
    __tablename__ = "news"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    story_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    source_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_url: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    publish_date: Mapped[date] = mapped_column(Date, nullable=False)
    language: Mapped[str] = mapped_column(String(8), nullable=False)
    media_name: Mapped[str] = mapped_column(String(64), nullable=False)
    perspective: Mapped[str] = mapped_column(String(32), nullable=False)
    description_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    enrich_status: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    title_zh: Mapped[str] = mapped_column(Text, nullable=False)
    summary_zh: Mapped[str] = mapped_column(Text, nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    event_datetime: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    event_time_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_location_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_region: Mapped[str | None] = mapped_column(String(32), nullable=True)
    event_lat: Mapped[float | None] = mapped_column(Double, nullable=True)
    event_lng: Mapped[float | None] = mapped_column(Double, nullable=True)
    mentioned_vessels: Mapped[list] = mapped_column(JSONB, nullable=False)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_path: Mapped[str | None] = mapped_column(String, nullable=True)
    relevant: Mapped[bool] = mapped_column(Boolean, nullable=False)
    event_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("events.id"), nullable=True)

