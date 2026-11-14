"""OFFLINE DEMO FIXTURES — fake candidates served by FakeXClient until T07 lands.

Never presented as live data: every page that uses this client shows the
warning banner from OFFLINE_NOTE. Fixture IDs/names are marked `fixture_` so
they can never be confused with real X accounts.
"""

from src.integrations.fake_x_client import FakeXClient
from src.integrations.x_client import Post, Profile

OFFLINE_NOTE = (
    "⚠️ OFFLINE TEST CLIENT — discovery below runs on fixture data (FakeXClient), "
    "not the live X API. Live discovery activates once credentials are configured in `.env`."
)


def offline_client() -> FakeXClient:
    return FakeXClient(
        profiles=[
            Profile(id="90001", username="fixture_robo", name="Fixture Robo",
                    description="Founder building humanoid robots for warehouses. ex-PhD",
                    follower_count=4300),
            Profile(id="90002", username="fixture_llmdev", name="Fixture L",
                    description="ML engineer, LLM eval tooling, open source", follower_count=1800),
            Profile(id="90003", username="fixture_baker", name="Fixture B",
                    description="sourdough baker and garden blogger", follower_count=310),
        ],
        posts=[
            Post(id="fx_p1", author_id="90001", created_at="2026-11-10T00:00:00Z",
                 text="our humanoid gripper hit 98% pick accuracy — demo video soon, github will be open"),
            Post(id="fx_p2", author_id="90002", created_at="2026-11-09T00:00:00Z",
                 text="released a small benchmark dataset for agentic tool use"),
            Post(id="fx_p3", author_id="90003", created_at="2026-11-08T00:00:00Z",
                 text="my starter finally survived, crumb shot attached"),
        ],
    )
