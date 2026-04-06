from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class IndicatorCache(Base):
    """
    Persisted indicator computation results per instrument × timeframe × indicator config.

    `params_hash` is the hex-digest of a deterministic hash of indicator type + params dict,
    so cache hits are O(1) key lookups rather than JSON comparisons.

    `values` stores the raw numpy array as a JSON list of floats (NaN → null).
    `last_ts` is the timestamp of the most recent bar used in the computation — used to
    determine whether a cache entry needs to be extended with newer bars.
    """

    __tablename__ = "indicator_cache"
    __table_args__ = (
        UniqueConstraint(
            "instrument_id",
            "timeframe",
            "indicator_type",
            "params_hash",
            name="uq_indicator_cache_key",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instrument_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("instrument.id", ondelete="CASCADE"), nullable=False, index=True
    )
    timeframe: Mapped[str] = mapped_column(String(10), nullable=False)
    indicator_type: Mapped[str] = mapped_column(String(50), nullable=False)
    params_hash: Mapped[str] = mapped_column(String(32), nullable=False)
    params_json: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # human-readable, not used as key
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    last_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # JSON-encoded list of {key: str, values: list[float|null]} — one entry per output series
    series_json: Mapped[str] = mapped_column(Text, nullable=False)
