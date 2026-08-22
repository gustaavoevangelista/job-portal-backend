from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models import Base, Job
from ingest_common import get_existing_dedup_hashes


def test_get_existing_dedup_hashes_returns_only_existing_values():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    session = Session()
    session.add(
        Job(
            dedup_hash="existing-hash",
            source="source-a",
            title="Title",
            company="Company",
            url="https://example.com/job",
        )
    )
    session.commit()

    existing = get_existing_dedup_hashes(session, ["existing-hash", "missing-hash"])

    assert existing == {"existing-hash"}

    session.close()
