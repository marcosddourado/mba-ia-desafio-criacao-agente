from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, Index, String, UniqueConstraint, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _novo_codigo() -> str:
    return f"RSV-{uuid4().hex[:8].upper()}"


class ReservaModel(Base):
    __tablename__ = "reservas"

    # Canceladas ficam na tabela (status='cancelada'): o código nunca repete.
    codigo: Mapped[str] = mapped_column(String(16), primary_key=True, default=_novo_codigo)
    apartamento: Mapped[str] = mapped_column(String(8), index=True)
    area: Mapped[str] = mapped_column(String(32))
    data: Mapped[str] = mapped_column(String(10))  # AAAA-MM-DD
    status: Mapped[str] = mapped_column(String(16), default="ativa")
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    cancelado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Garantia 5: a exclusividade é decidida pelo banco, no instante da gravação.
    __table_args__ = (
        Index(
            "ux_reservas_area_data_ativa",
            "area",
            "data",
            unique=True,
            sqlite_where=text("status = 'ativa'"),
            postgresql_where=text("status = 'ativa'"),
        ),
    )


class VisitanteModel(Base):
    __tablename__ = "visitantes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    apartamento: Mapped[str] = mapped_column(String(8), index=True)
    nome: Mapped[str] = mapped_column(String(120))
    data: Mapped[str] = mapped_column(String(10))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (UniqueConstraint("apartamento", "nome", "data"),)


class SessaoModel(Base):
    __tablename__ = "sessoes"

    session_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    apartamento: Mapped[str] = mapped_column(String(8))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
