from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class SyntheticConstituent(Base):
    """
    Maps a synthetic instrument to each real constituent instrument it references.

    ticker_alias is the symbol token used inside the expression (e.g. 'SPY' in 'SPY/GLD').
    A synthetic may reference the same constituent multiple times under different aliases
    (e.g. 'SPY*2 - SPY' would still only produce one row).
    """

    __tablename__ = "synthetic_constituent"
    __table_args__ = (
        UniqueConstraint(
            "synthetic_instrument_id", "ticker_alias", name="uq_synthetic_constituent"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    synthetic_instrument_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("instrument.id", ondelete="CASCADE"), nullable=False, index=True
    )
    constituent_instrument_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("instrument.id", ondelete="CASCADE"), nullable=False
    )
    # The ticker string used inside the expression, e.g. 'SPY', 'GLD'
    ticker_alias: Mapped[str] = mapped_column(String(50), nullable=False)

    synthetic_instrument: Mapped["Instrument"] = relationship(  # type: ignore[name-defined]
        foreign_keys=[synthetic_instrument_id], back_populates="synthetic_constituents"
    )
    constituent_instrument: Mapped["Instrument"] = relationship(  # type: ignore[name-defined]
        foreign_keys=[constituent_instrument_id]
    )
