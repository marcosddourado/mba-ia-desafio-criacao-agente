from datetime import datetime, timezone

from sqlalchemy import select, update

from db.engine import async_session
from db.models import ReservaModel, SessaoModel, VisitanteModel


# RESERVAS ############################
async def listar_reservas_ativas(apartamento: str) -> list[ReservaModel]:
    async with async_session.begin() as session:
        result = await session.execute(
            select(ReservaModel)
            .where(ReservaModel.apartamento == apartamento, ReservaModel.status == "ativa")
            .order_by(ReservaModel.data)
        )
        return list(result.scalars())


async def reserva_ativa_existe(area: str, data: str) -> bool:
    async with async_session.begin() as session:
        result = await session.execute(
            select(ReservaModel.codigo).where(
                ReservaModel.area == area,
                ReservaModel.data == data,
                ReservaModel.status == "ativa",
            )
        )
        return result.first() is not None


async def criar_reserva(apartamento: str, area: str, data: str) -> ReservaModel:
    """Deixa `IntegrityError` subir (índice único parcial): quem trata é a tool."""
    async with async_session.begin() as session:
        reserva = ReservaModel(apartamento=apartamento, area=area, data=data)
        session.add(reserva)
        await session.flush()
        return reserva


async def cancelar_reserva(apartamento: str, codigo: str) -> ReservaModel | None:
    """`None` se o código não é deste apartamento ou não está ativo (sem revelar o dono)."""
    async with async_session.begin() as session:
        result = await session.execute(
            update(ReservaModel)
            .where(
                ReservaModel.codigo == codigo,
                ReservaModel.apartamento == apartamento,
                ReservaModel.status == "ativa",
            )
            .values(status="cancelada", cancelado_em=datetime.now(timezone.utc))
            .returning(ReservaModel)
        )
        return result.scalars().first()


# VISITANTES ############################
async def listar_visitantes(apartamento: str) -> list[VisitanteModel]:
    async with async_session.begin() as session:
        result = await session.execute(
            select(VisitanteModel)
            .where(VisitanteModel.apartamento == apartamento)
            .order_by(VisitanteModel.data, VisitanteModel.id)
        )
        return list(result.scalars())


async def autorizar_visitante(apartamento: str, nome: str, data: str) -> VisitanteModel:
    """Deixa `IntegrityError` subir (`UNIQUE(apartamento, nome, data)`)."""
    async with async_session.begin() as session:
        visitante = VisitanteModel(apartamento=apartamento, nome=nome, data=data)
        session.add(visitante)
        await session.flush()
        return visitante


# SESSÕES ############################
async def criar_sessao(session_id: str, apartamento: str) -> SessaoModel:
    async with async_session.begin() as session:
        sessao = SessaoModel(session_id=session_id, apartamento=apartamento)
        session.add(sessao)
        await session.flush()
        return sessao


async def obter_sessao(session_id: str) -> SessaoModel | None:
    async with async_session.begin() as session:
        return await session.get(SessaoModel, session_id)
