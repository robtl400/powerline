from app.models.user import User  # noqa: F401 — imported so Alembic can see all models
from app.models.target import Target  # noqa: F401
from app.models.campaign import Campaign  # noqa: F401
from app.models.campaign_target import CampaignTarget  # noqa: F401
from app.models.phone_number import PhoneNumber  # noqa: F401
from app.models.campaign_phone_number import CampaignPhoneNumber  # noqa: F401
from app.models.audio import AudioRecording  # noqa: F401
from app.models.blocklist import BlocklistEntry  # noqa: F401
# CallSession must be imported before Call — Call.session relationship resolves "CallSession" by name
from app.models.call_session import CallSession  # noqa: F401
from app.models.call import Call  # noqa: F401
