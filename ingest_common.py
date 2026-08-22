from typing import Iterable

from sqlalchemy.orm import Session

from models import Job


def get_existing_dedup_hashes(session: Session, dedup_hashes: Iterable[str]) -> set[str]:
    """Return the dedup hashes already present in the database for a batch."""
    normalized_hashes = {dedup_hash for dedup_hash in dedup_hashes if dedup_hash}
    if not normalized_hashes:
        return set()

    rows = (
        session.query(Job.dedup_hash)
        .filter(Job.dedup_hash.in_(list(normalized_hashes)))
        .all()
    )
    return {row[0] for row in rows}
