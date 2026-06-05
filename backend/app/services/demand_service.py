from typing import Optional

from sqlalchemy.orm import Session

from app.models.assignment_rule import AssignmentRule
from app.models.demand import Demand, DemandStatus
from app.models.user import User
from app.services.audit_service import log_event


def find_continuity_user(db: Session, sender_email: str) -> Optional[int]:
    rule = (
        db.query(AssignmentRule)
        .join(User, User.id == AssignmentRule.assigned_user_id)
        .filter(
            AssignmentRule.sender_email == sender_email.lower(),
            AssignmentRule.active.is_(True),
            User.active.is_(True),
        )
        .first()
    )
    return rule.assigned_user_id if rule else None


def upsert_assignment_rule(db: Session, sender_email: str, user_id: int) -> AssignmentRule:
    sender = sender_email.lower()
    rule = db.query(AssignmentRule).filter(AssignmentRule.sender_email == sender).first()
    if rule:
        rule.assigned_user_id = user_id
        rule.active = True
    else:
        rule = AssignmentRule(sender_email=sender, assigned_user_id=user_id)
        db.add(rule)
    db.flush()
    return rule


def _notify_assigned(db: Session, user_id: int, demand: Demand, actor_name: str) -> None:
    from app.models.notification import Notification
    subject_preview = (demand.subject or demand.sender_email or "")[:80]
    db.add(Notification(
        user_id=user_id, demand_id=demand.id, type="DEMAND_ASSIGNED",
        message=f"{actor_name} atribuiu uma demanda a você: {subject_preview}",
    ))


def assign_demand(db: Session, demand: Demand, user: User, actor: User, bulk: bool = False) -> Demand:
    demand.assigned_user_id = user.id
    upsert_assignment_rule(db, demand.sender_email, user.id)
    if user.id != actor.id:
        _notify_assigned(db, user.id, demand, actor.name)
    log_event(
        db,
        event_type="DEMAND_ASSIGNED",
        description=f"Demanda atribuída a {user.name} ({user.email}) por {actor.name}",
        user_id=actor.id,
        demand_id=demand.id,
        metadata={"assigned_user_id": user.id, "bulk": bulk},
        commit=False,
    )

    bulk_count = 0
    if bulk:
        # Atribui todas as outras demandas do mesmo remetente que estejam:
        # - sem responsavel, OU
        # - ja com este mesmo usuario
        # NAO mexe em demandas atribuidas a OUTRAS pessoas.
        from sqlalchemy import or_
        others = db.query(Demand).filter(
            Demand.sender_email == demand.sender_email,
            Demand.id != demand.id,
            or_(Demand.assigned_user_id.is_(None), Demand.assigned_user_id == user.id),
        ).all()
        for d in others:
            if d.assigned_user_id != user.id:
                d.assigned_user_id = user.id
                bulk_count += 1
                log_event(
                    db, event_type="DEMAND_ASSIGNED",
                    description=f"Atribuição em lote: {user.name} (origem demanda #{demand.id})",
                    user_id=actor.id, demand_id=d.id,
                    metadata={"assigned_user_id": user.id, "bulk_origin": demand.id},
                    commit=False,
                )
        if bulk_count:
            log_event(
                db, event_type="DEMAND_BULK_ASSIGNED",
                description=f"{actor.name} atribuiu {bulk_count} demandas de '{demand.sender_email}' a {user.name}",
                user_id=actor.id, demand_id=demand.id,
                metadata={"sender_email": demand.sender_email, "count": bulk_count, "user_id": user.id},
                commit=False,
            )
    db.commit()
    db.refresh(demand)
    return demand


def assume_demand(db: Session, demand: Demand, actor: User, bulk: bool = False) -> Demand:
    if demand.assigned_user_id and demand.assigned_user_id != actor.id:
        raise ValueError("Demanda já atribuída a outro usuário")
    demand.assigned_user_id = actor.id
    upsert_assignment_rule(db, demand.sender_email, actor.id)
    log_event(
        db,
        event_type="DEMAND_ASSUMED",
        description=f"Demanda assumida por {actor.name}",
        user_id=actor.id, demand_id=demand.id,
        metadata={"bulk": bulk},
        commit=False,
    )

    bulk_count = 0
    if bulk:
        from sqlalchemy import or_
        others = db.query(Demand).filter(
            Demand.sender_email == demand.sender_email,
            Demand.id != demand.id,
            or_(Demand.assigned_user_id.is_(None), Demand.assigned_user_id == actor.id),
        ).all()
        for d in others:
            if d.assigned_user_id != actor.id:
                d.assigned_user_id = actor.id
                bulk_count += 1
                log_event(
                    db, event_type="DEMAND_ASSUMED",
                    description=f"Assumida em lote por {actor.name} (origem demanda #{demand.id})",
                    user_id=actor.id, demand_id=d.id,
                    metadata={"bulk_origin": demand.id},
                    commit=False,
                )
        if bulk_count:
            log_event(
                db, event_type="DEMAND_BULK_ASSIGNED",
                description=f"{actor.name} assumiu {bulk_count} demandas de '{demand.sender_email}' em lote",
                user_id=actor.id, demand_id=demand.id,
                metadata={"sender_email": demand.sender_email, "count": bulk_count, "user_id": actor.id},
                commit=False,
            )
    db.commit()
    db.refresh(demand)
    return demand


def unassign_demand(db: Session, demand: Demand, actor: User, remove_rule: bool = True, bulk: bool = False) -> Demand:
    """Remove responsavel da demanda. Por padrao tambem remove a regra de
    continuidade (senao o proximo e-mail desse remetente seria auto-atribuido).
    Se bulk=True, remove responsavel de todas as demandas do mesmo remetente."""
    previous_user_id = demand.assigned_user_id
    demand.assigned_user_id = None
    if remove_rule:
        rule = db.query(AssignmentRule).filter(AssignmentRule.sender_email == demand.sender_email.lower()).first()
        if rule:
            db.delete(rule)
    log_event(
        db,
        event_type="DEMAND_UNASSIGNED",
        description=f"{actor.name} removeu o responsavel da demanda" + (" e a regra de continuidade" if remove_rule else ""),
        user_id=actor.id, demand_id=demand.id,
        metadata={"previous_user_id": previous_user_id, "rule_removed": remove_rule, "bulk": bulk},
        commit=False,
    )

    if bulk:
        others = db.query(Demand).filter(
            Demand.sender_email == demand.sender_email,
            Demand.id != demand.id,
            Demand.assigned_user_id.isnot(None),
        ).all()
        for d in others:
            d.assigned_user_id = None
            log_event(
                db, event_type="DEMAND_UNASSIGNED",
                description=f"Remoção em lote por {actor.name} (origem demanda #{demand.id})",
                user_id=actor.id, demand_id=d.id,
                metadata={"previous_user_id": previous_user_id, "bulk_origin": demand.id},
                commit=False,
            )

    db.commit()
    db.refresh(demand)
    return demand


def change_status(db: Session, demand: Demand, new_status: DemandStatus, actor: User) -> Demand:
    old = demand.status
    demand.status = new_status
    log_event(
        db,
        event_type="DEMAND_STATUS_CHANGED",
        description=f"Status alterado de {old.value} para {new_status.value}",
        user_id=actor.id,
        demand_id=demand.id,
        metadata={"from": old.value, "to": new_status.value},
        commit=False,
    )
    db.commit()
    db.refresh(demand)
    return demand
